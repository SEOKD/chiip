"""AI 프론티어 랩 월별 ARR·분기 매출 — 공시·보도 뼈대 + 표시된 추정층 (마스터 지시 2026-11-14 "다시 만들어").

입력(knowledge/models/ai_labs/)
  arr_ledger.csv               공개 보도·공시 ARR 장부(유형·총액/순액·차트 사용 primary 표시)
  anthropic_s1_quarterly.csv   Anthropic S-1/A(2026-11-10) 분기 GAAP 매출 7개 분기
출력
  arr_monthly.json    {rows, meta}  랩·월별 월말 ARR — kind reported(장부 primary) / estimate(Chiip 추정)
  arr_quarterly.json  {rows, meta}  랩·분기 매출 — kind filing(공시 실적) / estimate(Chiip 추정)

추정 방법(보간을 숨기지 않는다 — 추정은 kind=estimate, 범위 lo~hi와 함께)
  Anthropic: 분기마다 월 매출을 등비(공비 r_q)로 놓아 분기 합계를 공시 실적과 정확히 맞추고,
             보도된 ARR 기준점(로그 오차)과 분기 경계의 성장 연속성을 함께 최소화하도록 r_q를 좌표 탐색으로 고른다.
             월말 ARR = 12 × 그 달 매출 × (월 성장률)^0.5. 범위 = 기준점 로그 잔차 RMS.
  OpenAI:    공시가 없다. 순액 기준 primary 보도값 사이를 로그 선형(일정 성장률)으로 잇는다.
             범위 = 기준점 하나씩 빼고 이웃으로 맞힌 로그 오차 RMS(leave-one-out).
  마지막 보도·공시 뒤 달은 추정하지 않는다(외삽 = 전망이라 하지 않음).
  분기 매출: Anthropic은 공시 실적. OpenAI는 월 ARR/12의 분기 합(추정).
사용: py scripts/industry/ai_arr.py [--show]
"""
import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "knowledge" / "models" / "ai_labs"
LABS = ("OpenAI", "Anthropic")
LAMBDA = 4.0          # 분기 경계 성장 연속성 가중(기준점 1개 = 1)
GRID = [1.0 + i * 0.005 for i in range(0, 161)]   # 월 공비 1.00~1.80


def months(a, b):
    y, m = int(a[:4]), int(a[5:7])
    out = []
    while True:
        k = f"{y}-{m:02d}"
        out.append(k)
        if k >= b:
            return out
        m += 1
        if m > 12:
            m, y = 1, y + 1


def frac(as_of):
    """기준일의 달 안 위치(0~1). 일자가 없으면 달 중간."""
    if len(as_of) >= 10:
        import calendar
        y, m, d = int(as_of[:4]), int(as_of[5:7]), int(as_of[8:10])
        return d / calendar.monthrange(y, m)[1]
    return 0.5


def ledger():
    return list(csv.DictReader(open(DIR / "arr_ledger.csv", encoding="utf-8")))


def anchors(rows, lab):
    out = [r for r in rows if r["lab"] == lab and r["primary"] == "1" and not (lab == "OpenAI" and r["basis"] == "gross")]
    return sorted(out, key=lambda r: r["as_of"])


def rms(xs):
    return math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else 0.0


# ---------- Anthropic: 분기 실적 + ARR 기준점 ----------
def anthropic(rows):
    q = list(csv.DictReader(open(DIR / "anthropic_s1_quarterly.csv", encoding="utf-8")))
    qmon = []                       # [(quarter, [m1,m2,m3], 매출 $B)]
    for r in q:
        y, mm = int(r["period_end"][:4]), int(r["period_end"][5:7])
        ms = [f"{y}-{mm - 2 + i:02d}" for i in range(3)]
        qmon.append((r["quarter"], ms, float(r["revenue_musd"]) / 1000))
    span = [m for _, ms, _ in qmon for m in ms]
    anc = [a for a in anchors(rows, "Anthropic") if a["as_of"][:7] in span]

    def path(rs):
        rev = {}
        for (qq, ms, s), r in zip(qmon, rs):
            w = [r ** i for i in range(3)]
            for m, wi in zip(ms, w):
                rev[m] = s * wi / sum(w)
        return rev

    def growth(rev, rs, m):
        i = span.index(m)
        if i + 1 < len(span):
            return rev[span[i + 1]] / rev[m]
        return rs[-1]

    def arr_at(rev, rs, m, f):
        return 12 * rev[m] * growth(rev, rs, m) ** (f - 0.5)

    def loss(rs):
        rev = path(rs)
        e = sum((math.log(arr_at(rev, rs, a["as_of"][:7], frac(a["as_of"])) / float(a["arr_usd_b"]))) ** 2 for a in anc)
        for i in range(len(qmon) - 1):   # 분기 경계: 다음 분기 첫 달/이번 분기 끝 달 성장이 두 분기 공비의 기하평균과 같도록
            last, first = rev[qmon[i][1][2]], rev[qmon[i + 1][1][0]]
            e += LAMBDA * (math.log(first / last) - 0.5 * math.log(rs[i] * rs[i + 1])) ** 2
        return e

    rs = [1.2] * len(qmon)
    for _ in range(40):
        before = list(rs)
        for i in range(len(rs)):
            best = min(GRID, key=lambda g: loss(rs[:i] + [g] + rs[i + 1:]))
            rs[i] = best
        if rs == before:
            break
    rev = path(rs)
    resid = [math.log(arr_at(rev, rs, a["as_of"][:7], frac(a["as_of"])) / float(a["arr_usd_b"])) for a in anc]
    band = rms(resid)
    est = {m: arr_at(rev, rs, m, 1.0) for m in span}       # 월말 ARR
    fit = {"monthly_ratio_by_quarter": {qq: round(r, 3) for (qq, _, _), r in zip(qmon, rs)},
           "anchor_log_rmse": round(band, 4), "anchors_used": len(anc),
           "anchor_resid": [{"as_of": a["as_of"], "reported": float(a["arr_usd_b"]), "model": round(math.exp(e) * float(a["arr_usd_b"]), 2)} for a, e in zip(anc, resid)]}
    quarterly = [{"quarter": qq, "lab": "Anthropic", "revenue_b": round(s, 3), "kind": "filing", "lo": round(s, 3), "hi": round(s, 3),
                  "annualized_b": round(4 * s, 2), "source": "S-1/A 2026-11-10"} for qq, _, s in qmon]
    return est, band, fit, quarterly


# ---------- OpenAI: 보도값 사이 로그 선형 ----------
def openai(rows):
    anc = anchors(rows, "OpenAI")
    pts = []                                   # (월 번호, log ARR)
    for a in anc:
        y, m = int(a["as_of"][:4]), int(a["as_of"][5:7])
        pts.append((y * 12 + m - 1 + frac(a["as_of"]) - 1.0, math.log(float(a["arr_usd_b"]))))   # 월말 기준 위치로
    def interp(t, ps):
        for (t0, v0), (t1, v1) in zip(ps, ps[1:]):
            if t0 <= t <= t1:
                return v0 + (v1 - v0) * (t - t0) / (t1 - t0) if t1 > t0 else v0
        return None
    loo = []
    for i in range(1, len(pts) - 1):
        v = interp(pts[i][0], pts[:i] + pts[i + 1:])
        if v is not None:
            loo.append(v - pts[i][1])
    band = rms(loo)
    first, last = anc[0]["as_of"][:7], anc[-1]["as_of"][:7]
    est = {}
    for m in months(first, last):
        t = int(m[:4]) * 12 + int(m[5:7]) - 1          # 그 달 말
        v = interp(t, pts)
        if v is not None:
            est[m] = math.exp(v)
    fit = {"loo_log_rmse": round(band, 4), "anchors_used": len(anc),
           "loo_resid": [round(x, 3) for x in loo]}
    return est, band, fit


def build():
    rows = ledger()
    a_est, a_band, a_fit, quarterly = anthropic(rows)
    o_est, o_band, o_fit = openai(rows)
    rep = {}
    for lab in LABS:
        for a in anchors(rows, lab):
            rep[(lab, a["as_of"][:7])] = a
    allm = months("2025-01", max(m for (_, m) in rep))
    out = []
    for lab, est, band in (("OpenAI", o_est, o_band), ("Anthropic", a_est, a_band)):
        for m in allm:
            r = rep.get((lab, m))
            if r:
                v = float(r["arr_usd_b"])
                out.append({"key": f"{m}|{lab}", "month": m, "lab": lab, "arr": v, "kind": "reported",
                            "lo": v, "hi": v, "type": r["type"], "basis": r["basis"], "publisher": r["publisher"],
                            "as_of": r["as_of"], "ledger_id": r["id"],
                            "model": round(est[m], 2) if m in est else None})
            elif m in est:
                v = est[m]
                out.append({"key": f"{m}|{lab}", "month": m, "lab": lab, "arr": round(v, 2), "kind": "estimate",
                            "lo": round(v * math.exp(-band), 2), "hi": round(v * math.exp(band), 2), "type": "chiip_estimate",
                            "basis": "net" if lab == "OpenAI" else "gross", "publisher": "Chiip 추정",
                            "as_of": m + " 말", "ledger_id": "", "model": round(v, 2)})
    # OpenAI 분기 매출 추정 = 월 ARR/12 합(월 중간값 근사: 전월 말·당월 말 기하평균)
    om = {r["month"]: r for r in out if r["lab"] == "OpenAI"}
    for qq, ms in (("1Q25", ["2025-01", "2025-02", "2025-03"]), ("2Q25", ["2025-04", "2025-05", "2025-06"]),
                   ("3Q25", ["2025-07", "2025-08", "2025-09"]), ("4Q25", ["2025-10", "2025-11", "2025-12"]),
                   ("1Q26", ["2026-01", "2026-02", "2026-03"]), ("2Q26", ["2026-04", "2026-05", "2026-06"]),
                   ("3Q26", ["2026-07", "2026-08", "2026-09"])):
        prev = months("2024-12", ms[0])[-2]
        seq = [prev] + ms
        v = {m: (om[m]["arr"] if m in om else o_est.get(m)) for m in seq}   # 2024-12는 기준점(장부) 값
        if any(x is None for x in v.values()):
            continue
        s = sum(math.sqrt(v[seq[i]] * v[seq[i + 1]]) / 12 for i in range(3))
        quarterly.append({"quarter": qq, "lab": "OpenAI", "revenue_b": round(s, 3), "kind": "estimate",
                          "lo": round(s * math.exp(-o_band), 3), "hi": round(s * math.exp(o_band), 3),
                          "annualized_b": round(4 * s, 2), "source": "Chiip 추정(보도 ARR 로그 선형)"})
    quarterly.sort(key=lambda r: (r["quarter"][2:] + r["quarter"][:2], r["lab"]))
    code = Path(__file__).read_text(encoding="utf-8")
    meta = [{"label": "ai_arr.py", "value": code, "type": "code", "lang": "python"},
            {"label": "Input", "value": "arr_ledger.csv, anthropic_s1_quarterly.csv"},
            {"label": "Anthropic fit", "value": json.dumps(a_fit, ensure_ascii=False)},
            {"label": "OpenAI fit", "value": json.dumps(o_fit, ensure_ascii=False)}]
    json.dump({"rows": out, "meta": meta}, open(DIR / "arr_monthly.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"rows": quarterly, "meta": meta}, open(DIR / "arr_quarterly.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return out, quarterly, a_fit, o_fit


if __name__ == "__main__":
    out, q, af, of = build()
    if "--show" in sys.argv:
        print(json.dumps(af, ensure_ascii=False))
        print(json.dumps(of, ensure_ascii=False))
        for r in out:
            print(r["month"], r["lab"], r["kind"], r["arr"], r["lo"], r["hi"], r.get("model"))
        for r in q:
            print(r["quarter"], r["lab"], r["kind"], r["revenue_b"], r["annualized_b"])
