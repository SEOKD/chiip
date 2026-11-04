"""모델 포트폴리오 성과 귀속·학습 4단계 (마스터 지시 2026-11-04 "4단계 진행", 설계 knowledge/methods/portfolio_management_design.md 2절 ⑦·3절)

연구용 가상 장부(scripts/pm/ledger.py)의 성적표다 — 매매·비중 지시가 아니다.
  성과        누적·연 변동성·샤프(rf 차감)·최대 낙폭, SPY 대비 초과·추적 오차·정보 비율
  팩터 귀속   장부 일간 수익 = a + β·SPY + Σ γ_k·(테마 ETF의 SPY 잔차) + e — 연율 a가 '테마 베타가 아닌 몫'
  브린슨      장부 vs HRP 기준선, 테마 군집별 배분 효과·선택 효과(Brinson, Hood & Beebower 1986)
  실현 IC     점수 이력(score_hist.jsonl의 합성 기대수익 μ) vs 다음 h거래일 수익의 순위 상관, 날짜별 평균
  전이 계수   TC = corr(구성 비중, μ/σ²)(Clarke, de Silva & Thorley 2002) — 제약이 판단을 얼마나 깎나
  수축 샤프   DSR = Φ((SR − SR0)·√(T−1) / √(1 − γ3·SR + (γ4−1)/4·SR²)), SR0 = 시도 N개의 기대 최대 샤프(Bailey & López de Prado 2014)
  MinTRL      그 샤프가 0보다 크다고 말하려면 필요한 최소 관측 수
  재보정 관문 추정 상수(IC)만 제안: 관측 ≥ min_days · DSR ≥ dsr_min · 구성 장부가 HRP를 이김 → knowledge/models/pm/recal_proposal.json
              (config를 바꾸지 않는다 — Model Lab 일요일 채택·상대 변화 20% 이상은 마스터 승인). 위험 정책 상수는 제안하지도 않는다.
사용: py scripts/pm/attribution.py      → knowledge/models/pm/attribution.json
"""
import csv
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "pm"))
import risk  # noqa: E402

DIR = ROOT / "knowledge" / "models" / "pm"
KST = timezone(timedelta(hours=9))
EULER = 0.5772156649
N01 = NormalDist()


def book_returns():
    """{장부: {날짜: 수익}} — 시가평가 행(ret)과 거래 비용 행(cost)을 합친다"""
    out = {}
    p = DIR / "book_log.csv"
    if not p.exists():
        return out
    with p.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            b = out.setdefault(r["book"], {})
            if r.get("ret") not in ("", None):
                b[r["date"]] = b.get(r["date"], 0.0) + float(r["ret"])
            if r.get("cost") not in ("", None) and float(r["cost"] or 0):
                b[r["date"]] = b.get(r["date"], 0.0) - float(r["cost"])
    return out


def moments(x):
    n = len(x)
    m = sum(x) / n
    v = sum((a - m) ** 2 for a in x) / (n - 1) if n > 1 else 0.0
    s = math.sqrt(v)
    if not s:
        return m, 0.0, 0.0, 3.0
    g3 = sum(((a - m) / s) ** 3 for a in x) / n
    g4 = sum(((a - m) / s) ** 4 for a in x) / n
    return m, s, g3, g4


def perf(r, rf, ann=252):
    days = sorted(r)
    x = [r[d] - rf / ann for d in days]
    m, s, g3, g4 = moments(x)
    eq, pk, mdd = 1.0, 1.0, 0.0
    for d in days:
        eq *= 1 + r[d]
        pk = max(pk, eq)
        mdd = max(mdd, 1 - eq / pk)
    return {"days": len(days), "cum": round(eq - 1, 4), "vol_ann": round(s * math.sqrt(ann), 4),
            "sharpe_ann": round(m / s * math.sqrt(ann), 3) if s else None, "sr_daily": m / s if s else 0.0, "skew": g3, "kurt": g4, "max_dd": round(mdd, 4)}


def dsr(sr, T, g3, g4, sr_trials):
    """수축 샤프(일 단위 SR). sr_trials = 시도한 설정들의 SR 목록"""
    N = max(len(sr_trials), 1)
    if T < 3:
        return None
    var = sum((a - sum(sr_trials) / N) ** 2 for a in sr_trials) / (N - 1) if N > 1 else 0.0
    sr0 = math.sqrt(var) * ((1 - EULER) * N01.inv_cdf(1 - 1 / N) + EULER * N01.inv_cdf(1 - 1 / (N * math.e))) if N > 1 and var > 0 else 0.0
    den = 1 - g3 * sr + (g4 - 1) / 4 * sr * sr
    return round(N01.cdf((sr - sr0) * math.sqrt(T - 1) / math.sqrt(den)), 4) if den > 0 else None


def min_trl(sr, g3, g4, alpha=0.05, sr_star=0.0):
    if sr <= sr_star:
        return None
    return math.ceil(1 + (1 - g3 * sr + (g4 - 1) / 4 * sr * sr) * (N01.inv_cdf(1 - alpha) / (sr - sr_star)) ** 2)


def ols_multi(Y, Xs):
    """Y ~ 1 + Xs(열 목록). 반환 계수 [a, b1, …]"""
    sys.path.insert(0, str(ROOT / "scripts" / "pm"))
    import construct
    n = len(Y)
    X = [[1.0] + [col[t] for col in Xs] for t in range(n)]
    k = len(X[0])
    XtX = [[sum(X[t][i] * X[t][j] for t in range(n)) for j in range(k)] for i in range(k)]
    XtY = [sum(X[t][i] * Y[t] for t in range(n)) for i in range(k)]
    return construct.mv(construct.inv(XtX), XtY)


def factor_attr(r, series, c, ann=252):
    mk = c["universe"]["market"]
    th = c["universe"]["themes"]
    days = [d for d in sorted(r) if d in series.get(mk, {}) and all(d in series.get(s, {}) for s in th.values())]
    if len(days) < c["attribution"]["min_days_factor"]:
        return {"days": len(days), "verdict": "표본 부족"}
    m = [series[mk][d] for d in days]
    cols = []
    for s in th.values():
        bt = risk.ols_beta(m, [series[s][d] for d in days])
        cols.append([series[s][d] - bt * series[mk][d] for d in days])
    coef = ols_multi([r[d] for d in days], [m] + cols)
    return {"days": len(days), "alpha_ann": round(coef[0] * ann, 4), "beta": round(coef[1], 2),
            "themes": {k: round(v, 2) for k, v in zip(th, coef[2:])}}


def brinson(books, series, groups):
    """장부(구성) vs HRP — 군집별 배분·선택 효과 합(일별 누적 단순 합)"""
    snaps = {}
    p = DIR / "weights_log.jsonl"
    if not p.exists():
        return None
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            j = json.loads(line)
            snaps.setdefault(j["book"], {})[j["date"]] = j["w"]
    port, bench = snaps.get("구성", {}), snaps.get("HRP", {})
    days = sorted(set(port) & set(bench))
    if not days:
        return None
    alloc, sel = {}, {}
    for d in days:
        rb_tot = sum(w * series.get(s, {}).get(d, 0.0) for s, w in bench[d].items())
        for g, members in groups.items():
            wp = sum(port[d].get(s, 0.0) for s in members)
            wb = sum(bench[d].get(s, 0.0) for s in members)
            rp = sum(port[d].get(s, 0.0) * series.get(s, {}).get(d, 0.0) for s in members) / wp if wp else 0.0
            rb = sum(bench[d].get(s, 0.0) * series.get(s, {}).get(d, 0.0) for s in members) / wb if wb else 0.0
            alloc[g] = alloc.get(g, 0.0) + (wp - wb) * (rb - rb_tot)
            sel[g] = sel.get(g, 0.0) + wp * (rp - rb)
    return {"days": len(days), "allocation": {g: round(v, 5) for g, v in alloc.items()}, "selection": {g: round(v, 5) for g, v in sel.items()}}


def spearman(a, b):
    def rank(x):
        o = sorted(range(len(x)), key=lambda i: x[i])
        rk = [0.0] * len(x)
        for pos, i in enumerate(o):
            rk[i] = pos
        return rk
    ra, rb = rank(a), rank(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va, vb = sum((x - ma) ** 2 for x in ra), sum((y - mb) ** 2 for y in rb)
    return cov / math.sqrt(va * vb) if va and vb else None


def realized_ic(px, h):
    p = DIR / "score_hist.jsonl"
    if not p.exists():
        return {"n_dates": 0}
    ics = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        j = json.loads(line)
        xs, ys = [], []
        for s, mu in (j.get("mu") or {}).items():
            bars = [b for b in px.get(s, []) if b[0] >= j["date"]]
            if len(bars) > h:
                xs.append(mu)
                ys.append(bars[h][1] / bars[0][1] - 1)
        if len(xs) >= 3:
            v = spearman(xs, ys)
            if v is not None:
                ics.append(v)
    return {"n_dates": len(ics), "ic_mean": round(sum(ics) / len(ics), 4) if ics else None}


def transfer_coef():
    cs = json.loads((DIR / "construct.json").read_text(encoding="utf-8")) if (DIR / "construct.json").exists() else {}
    rk = json.loads((DIR / "latest.json").read_text(encoding="utf-8")) if (DIR / "latest.json").exists() else {}
    xs, ys = [], []
    for s, r in (cs.get("rows") or {}).items():
        v = (rk.get("vol_ann") or {}).get(s)
        if v:
            xs.append(r["w"])
            ys.append(r["mu_bl"] / (v * v))
    if len(xs) < 3:
        return None
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    va, vb = sum((a - mx) ** 2 for a in xs), sum((b - my) ** 2 for b in ys)
    return round(cov / math.sqrt(va * vb), 3) if va and vb else None


def run():
    c = yaml.safe_load((ROOT / "config" / "pm.yaml").read_text(encoding="utf-8"))
    a = c["attribution"]
    rf = c["expected"]["rf"]
    px = risk.load_prices()
    series = {k: risk.returns(v) for k, v in px.items()}
    books = book_returns()
    perfs = {b: perf(r, rf) for b, r in books.items() if len(r) >= 2}
    trials = [p["sr_daily"] for p in perfs.values()] + [0.0] * max(0, a["trials_extra"])   # 시도 수 = 장부 + 과거에 버린 설정 수(보수적으로 더함)
    out = {"as_of": datetime.now(KST).isoformat(timespec="seconds"), "books": {}, "note": "연구용 가상 장부 성적표 — 매매·비중 지시가 아님"}
    spy = books.get("SPY", {})
    for b, p in perfs.items():
        row = {k: v for k, v in p.items() if k not in ("sr_daily", "skew", "kurt")}
        row["dsr"] = dsr(p["sr_daily"], p["days"], p["skew"], p["kurt"], trials)
        row["min_trl_days"] = min_trl(p["sr_daily"], p["skew"], p["kurt"])
        common = sorted(set(books[b]) & set(spy))
        if b != "SPY" and len(common) >= 2:
            act = [books[b][d] - spy[d] for d in common]
            m, s, _, _ = moments(act)
            row.update({"active_ann": round(m * 252, 4), "te_ann": round(s * math.sqrt(252), 4), "ir": round(m / s * math.sqrt(252), 3) if s else None})
        row["factor"] = factor_attr(books[b], series, c) if b != "SPY" else None
        out["books"][b] = row
    cs = json.loads((DIR / "construct.json").read_text(encoding="utf-8")) if (DIR / "construct.json").exists() else {}
    out["brinson_vs_hrp"] = brinson(books, series, cs.get("groups") or {})
    out["ic"] = realized_ic(px, a["ic_horizon"])
    out["transfer_coef"] = transfer_coef()
    # 재보정 관문 — 제안만
    comp, hrp = out["books"].get("구성") or {}, out["books"].get("HRP") or {}
    gate = {"days": comp.get("days", 0), "need_days": a["min_days"], "dsr": comp.get("dsr"), "need_dsr": a["dsr_min"],
            "beats_hrp": (comp.get("cum") or 0) > (hrp.get("cum") or 0) if comp and hrp else None, "ic_dates": out["ic"]["n_dates"]}
    ok = gate["days"] >= a["min_days"] and (gate["dsr"] or 0) >= a["dsr_min"] and gate["beats_hrp"] and out["ic"]["n_dates"] >= a["min_ic_dates"]
    gate["verdict"] = "제안 가능" if ok else "판정 보류 — 표본·검정 미달"
    if ok:
        n, k = out["ic"]["n_dates"], a["ic_prior_weight"]
        new_ic = (n * out["ic"]["ic_mean"] + k * c["expected"]["ic"]) / (n + k)   # 사전값 쪽으로 축소
        prop = {"date": out["as_of"][:10], "param": "prm-pm-expected-ic", "from": c["expected"]["ic"], "to": round(new_ic, 4),
                "rel_change": round(new_ic / c["expected"]["ic"] - 1, 3), "needs_master": abs(new_ic / c["expected"]["ic"] - 1) >= 0.20, "evidence": gate}
        (DIR / "recal_proposal.json").write_text(json.dumps(prop, ensure_ascii=False, indent=1), encoding="utf-8")
        gate["proposal"] = prop
    out["recal_gate"] = gate
    (DIR / "attribution.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    r = run()
    for b, x in r["books"].items():
        print(f"[PM 성적] {b}: {x['days']}일 · 누적 {x['cum']:+.2%} · 샤프 {x['sharpe_ann']} · 최대낙폭 {x['max_dd']:.1%} · DSR {x['dsr']} · MinTRL {x['min_trl_days']}")
    print(f"  실현 IC: {r['ic']} · 전이 계수 TC {r['transfer_coef']} · 재보정 관문: {r['recal_gate']['verdict']}")


if __name__ == "__main__":
    main(sys.argv[1:])
