"""인사이트(알파) 점수 성과 원장 (마스터 지시 2026-11-04 "점수 체계가 고도화돼 있는지 모델을 한 번 점검하라")

점검 결과 점수 상수가 피팅된 적이 없었다 — 점수와 그 뒤 주가 반응을 잇는 자료가 없었기 때문. 이 원장이 그 자료다.
  py scripts/insight/score_ledger.py log                 # Pulse 피드(outputs/article/sources/*_feed.json)의 건을 원장에 올린다(중복 없음)
  py scripts/insight/score_ledger.py due                 # 반응을 아직 못 채운 티커·발송일 → 모델이 TradingView 일봉을 받는다
  py scripts/insight/score_ledger.py resolve <가격 json> # {"SPY": [["2026-11-03", 680.1], …], "NVDA": [...]} 종가 → 1·5·20거래일 AR(β=1, 시장 SPY)
  py scripts/insight/score_ledger.py calibrate [--adopt] # 컨빅션 원점수 → 방향 적중 확률 보정(표본 외 브라이어 개선 시만 채택, 2026-11-04)
  py scripts/insight/score_ledger.py fit                 # 점수 구간별 |AR|·방향 적중, 스피어만 — 표본 외 30건(등록부 adoption.min_oos_n) 전에는 판정하지 않는다
방향: 피드 item의 "dir"(+1 유리·−1 불리·0 중립, 없으면 0). 점수 구성(parts: novelty·materiality·mispricing·conviction)이 있으면 같이 남긴다.
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "knowledge" / "models" / "insight" / "score_ledger.csv"
FEEDS = ROOT / "outputs" / "article" / "sources"
COLS = ["sent", "code", "name", "insight", "dir", "novelty", "materiality", "mispricing", "conviction", "ar1", "ar5", "ar20",
        "chain", "bridge", "priced", "nonobvious", "falsifier", "conv_raw", "conv_p"]   # 2026-11-04 재설계 열(해석 품질·컨빅션 원점수·확률)
INTERP = ("chain", "bridge", "priced", "nonobvious", "falsifier")
HORIZONS = (1, 5, 20)
MIN_N = 30


def rows():
    if not LEDGER.exists():
        return []
    with LEDGER.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save(rs):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, COLS, restval="")
        w.writeheader()
        w.writerows(rs)


def sent_at(path):
    s = path.stem.removesuffix("_feed")   # 20261104_1310
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[9:11]}:{s[11:13]}+09:00"


def log(feeds=None):
    rs = rows()
    have = {(r["sent"], r["code"]) for r in rs}
    n = 0
    for p in sorted(feeds or FEEDS.glob("*_feed.json")):
        for x in json.loads(p.read_text(encoding="utf-8")).get("items") or []:
            key = (sent_at(p), x.get("code") or "")
            if not key[1] or key in have:
                continue
            parts = x.get("parts") or {}
            rs.append({"sent": key[0], "code": key[1], "name": x.get("name", ""), "insight": x.get("insight"), "dir": x.get("dir", 0),
                       **{k: parts.get(k, "") for k in ("novelty", "materiality", "mispricing", "conviction") + INTERP},
                       "conv_raw": (x.get("conv") or {}).get("raw", ""), "conv_p": (x.get("conv") or {}).get("p_hit", ""),
                       "ar1": "", "ar5": "", "ar20": ""})
            have.add(key)
            n += 1
    save(rs)
    return n


def ar(series, mkt, day, h):
    """발송일 종가(장중 발송이면 그날 종가가 첫 반응을 담지 못하므로 전날 종가) 기준 h거래일 AR % — β=1"""
    s = sorted(series)
    m = dict(mkt)
    base = [i for i, (d, _) in enumerate(s) if d < day]
    if not base:
        return None
    i0 = base[-1]
    if i0 + h >= len(s):
        return None
    d0, c0 = s[i0]
    d1, c1 = s[i0 + h]
    if d0 not in m or d1 not in m:
        return None
    return round((c1 / c0 - m[d1] / m[d0]) * 100, 2)


def resolve(prices, market="SPY"):
    rs, n = rows(), 0
    mkt = prices.get(market) or []
    for r in rs:
        ser = prices.get(r["code"])
        if not ser:
            continue
        for h in HORIZONS:
            if r[f"ar{h}"] == "":
                v = ar(ser, mkt, r["sent"][:10], h)
                if v is not None:
                    r[f"ar{h}"] = v
                    n += 1
    save(rs)
    return n


def _rank(xs):
    o = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(o):
        j = i
        while j + 1 < len(o) and xs[o[j + 1]] == xs[o[i]]:
            j += 1
        for k in range(i, j + 1):
            r[o[k]] = (i + j) / 2
        i = j + 1
    return r


def spearman(a, b):
    ra, rb = _rank(a), _rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return cov / (va * vb) ** 0.5 if va and vb else None


def fit(h=5):
    done = [r for r in rows() if r[f"ar{h}"] != "" and r["insight"] not in ("", None)]
    out = {"horizon": h, "n": len(done), "min_n": MIN_N}
    if not done:
        return out
    sc = [float(r["insight"]) for r in done]
    mag = [abs(float(r[f"ar{h}"])) for r in done]
    out["spearman_score_absar"] = None if len(done) < 3 else round(spearman(sc, mag) or 0, 3)
    buckets = {}
    for s, r in zip(sc, done):
        b = "7+" if s >= 7 else "5~6" if s >= 5 else "~4"
        buckets.setdefault(b, []).append(r)
    out["buckets"] = {b: {"n": len(v), "mean_absar": round(sum(abs(float(r[f'ar{h}'])) for r in v) / len(v), 2),
                          "hit": (lambda d: round(sum(1 for r in d if float(r[f'ar{h}']) * float(r['dir']) > 0) / len(d), 2) if d else None)([r for r in v if float(r["dir"] or 0) != 0])}
                      for b, v in sorted(buckets.items())}
    out["spread"] = round(max(sc) - min(sc), 1)
    out["verdict"] = "표본 부족 — 판정 보류" if len(done) < MIN_N else ("점수가 반응 크기를 가른다" if (out["spearman_score_absar"] or 0) > 0.2 else "점수가 반응 크기를 가르지 못한다 — 경계값 재피팅 후보")
    return out


def brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)


def logit_fit(xs, ys, iters=50, ridge=1.0):
    """원점수 → 적중 확률 로지스틱(a + b·x), 뉴턴법 + 약한 능형 벌점(과적합 방지)"""
    a = b = 0.0
    for _ in range(iters):
        ga = gb = haa = hab = hbb = 0.0
        for x, y in zip(xs, ys):
            p = 1 / (1 + 2.718281828459045 ** -(a + b * x))
            w = p * (1 - p)
            ga += y - p
            gb += (y - p) * x
            haa += w
            hab += w * x
            hbb += w * x * x
        gb -= ridge * b
        hbb += ridge
        det = haa * hbb - hab * hab
        if not det:
            break
        a += (hbb * ga - hab * gb) / det
        b += (haa * gb - hab * ga) / det
    return a, b


def calibrate(h=5, adopt=False):
    """컨빅션 보정(마스터 지시 2026-11-04): 방향을 낸 건(dir≠0)의 5거래일 AR 부호 적중을 원점수로 회귀.
    시간순 앞 70%로 맞추고 뒤 30%(표본 외)에서 브라이어 점수를 사전 사상과 비교 — 표본 외 calib_min_oos건 이상 + 개선일 때만 채택"""
    import math
    sys.path.insert(0, str(ROOT / "scripts" / "insight"))
    import insight_calc as ic
    done = sorted((r for r in rows() if r[f"ar{h}"] != "" and r["conv_raw"] not in ("", None) and float(r["dir"] or 0) != 0), key=lambda r: r["sent"])
    xs = [float(r["conv_raw"]) for r in done]
    ys = [1 if float(r[f"ar{h}"]) * float(r["dir"]) > 0 else 0 for r in done]
    out = {"horizon": h, "n": len(done)}
    if done:
        buckets = {}
        for x, y in zip(xs, ys):
            buckets.setdefault("8~10" if x >= 8 else "5~7" if x >= 5 else "0~4", []).append(y)
        out["hit_by_raw"] = {k: {"n": len(v), "hit": round(sum(v) / len(v), 2)} for k, v in sorted(buckets.items())}
    cut = int(len(done) * 0.7)
    need = ic.P()["calib_min_oos"]
    if len(done) - cut < need:
        out["verdict"] = f"표본 외 {len(done) - cut}건 < {need} — 보정 보류(사전 사상 유지)"
        return out
    a, b = logit_fit(xs[:cut], ys[:cut])
    lo, hi = ic.P()["conviction_prior"]
    test_x, test_y = xs[cut:], ys[cut:]
    fitted = [1 / (1 + math.exp(-(a + b * x))) for x in test_x]
    prior = [lo + (hi - lo) * x / 10 for x in test_x]
    out.update({"a": round(a, 4), "b": round(b, 4), "brier_oos": round(brier(fitted, test_y), 4), "brier_prior": round(brier(prior, test_y), 4), "n_oos": len(test_x)})
    ok = out["brier_oos"] < out["brier_prior"] and b > 0
    out["verdict"] = "채택 가능" if ok else "개선 없음 — 사전 사상 유지"
    if adopt and ok:
        a2, b2 = logit_fit(xs, ys)   # 채택 시 전체 표본으로 다시 맞춘다
        (LEDGER.parent / "calibration.json").write_text(json.dumps({"a": round(a2, 4), "b": round(b2, 4), "n": len(xs), "brier_oos": out["brier_oos"],
                                                                    "brier_prior": out["brier_prior"], "horizon": h}, ensure_ascii=False, indent=1), encoding="utf-8")
        out["adopted"] = True
    return out


def due():
    return sorted({(r["code"], r["sent"][:10]) for r in rows() if r["ar20"] == ""})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if a[:1] == ["log"]:
        print(f"원장에 {log()}건 추가")
    elif a[:1] == ["due"]:
        print(json.dumps(due(), ensure_ascii=False))
    elif a[:1] == ["resolve"] and len(a) == 2:
        print(f"AR {resolve(json.loads(Path(a[1]).read_text(encoding='utf-8')))}칸 채움")
    elif a[:1] == ["fit"]:
        print(json.dumps(fit(int(a[1]) if len(a) > 1 else 5), ensure_ascii=False, indent=1))
    elif a[:1] == ["calibrate"]:   # 컨빅션 보정 — --adopt는 Model Lab 일요일 채택 관문에서만
        print(json.dumps(calibrate(adopt="--adopt" in a), ensure_ascii=False, indent=1))
    else:
        raise SystemExit(__doc__)
