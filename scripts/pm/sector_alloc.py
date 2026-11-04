"""Portfolio 섹터 배분 판단 체계 (마스터 지시 2026-11-04 "섹터별 역학 관계를 파악해 현 시장 상황과 미래의 시장 전망을 고려해 어떤 섹터를 고르는 게
추세추종·가치평가·알파 관점에서 수익률이 높고 섹터별 몇 % 비중으로 노출시켜야 수익률을 극대화할 수 있는지 — 전문 지식과 월스트리트 IB의 방법론과 기술")

연구용 모델 배분 지표다 — 마스터 계좌의 매매·비중 지시가 아니고, 마스터 포지션 파일을 읽지 않는다. 설정 config/sector_alloc.yaml(등록부 prm-sec-*).
  1. 재료     섹터마다 대형주 4곳 바스켓(Fiscal.ai, sector_alloc.js) → 시총 가중 12-1·6-1 모멘텀, 200일선 위 비중, EV/매출 3년 백분위, 30일 EPS 추정 변화
  2. 렌즈     추세추종(시계열·횡단면 모멘텀 + 200일 추세 필터) · 가치평가(자기 역사 대비 싼 정도) · 알파(이익 추정 수정 + 매크로 국면 적합)
              — 하위 신호마다 섹터 간 z, 렌즈 z = 가중 평균. 국면(위험 회피·선호, 금리 상승·하락)은 config tilts로 섹터 z에 더한다
  3. 기대수익  μ_s = Σ_렌즈 IC × σ_s × z (Grinold & Kahn 1999) — 렌즈별 기여를 따로 보여 준다
  4. 배분     블랙-리터만: 사전 = 벤치마크(바스켓 시총 비중, S&P 500 섹터 비중 근사)의 CAPM 균형 β×mrp, 견해 = μ_s, Ω = (1/c − 1)·τ·σ²
              → 제약 평균-분산(섹터 ±active_max, 상한 w_max, 합 100%) — 공분산은 섹터 ETF 일봉(EWMA + 레드와·울프 축소, scripts/pm/risk.py)
  5. 출력     섹터별 렌즈 z·기여·모델 비중·벤치마크 대비 → knowledge/models/portfolio/sector_alloc.json
사용: py scripts/pm/sector_alloc.py --code <0|1>   # execute_code 본문(종목 키 절반씩)
      py scripts/pm/sector_alloc.py --put <파일>    # Fiscal 출력 합치기
      py scripts/pm/sector_alloc.py                 # 계산
"""
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "pm"))
import construct  # noqa: E402
import risk  # noqa: E402

DIR = ROOT / "knowledge" / "models" / "portfolio"
IN = DIR / "sector_alloc_in.json"
OUT = DIR / "sector_alloc.json"
KST = timezone(timedelta(hours=9))
FIELDS = ["key", "mcap_b", "r21", "r126", "r252", "above200", "evs_pct3y", "rev30"]


def cfg():
    return yaml.safe_load((ROOT / "config" / "sector_alloc.yaml").read_text(encoding="utf-8"))


def keys(c=None):
    return [k for s in (c or cfg())["sectors"].values() for k in s["keys"]]


def code(part):
    ks = keys()
    h = (len(ks) + 1) // 2
    js = (ROOT / "scripts" / "pm" / "sector_alloc.js").read_text(encoding="utf-8")
    return js.replace("__KEYS__", json.dumps(ks[:h] if part == 0 else ks[h:]))


def put(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    have = json.loads(IN.read_text(encoding="utf-8")) if IN.exists() else {"rows": {}}
    for r in d.get("rows") or []:
        have["rows"][r[0]] = dict(zip(FIELDS, r))
    have["as_of"] = datetime.now(KST).isoformat(timespec="seconds")
    IN.write_text(json.dumps(have, ensure_ascii=False), encoding="utf-8")
    return len(d.get("rows") or [])


def zs(vals):
    xs = [v for v in vals.values() if v is not None]
    if len(xs) < 3:
        return {k: 0.0 for k in vals}
    m = sum(xs) / len(xs)
    s = math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) or 1.0
    return {k: 0.0 if v is None else max(-3.0, min(3.0, (v - m) / s)) for k, v in vals.items()}


def aggregate(c, rows):
    """섹터 = 바스켓 시총 가중(시총 없으면 동일)"""
    out = {}
    for name, s in c["sectors"].items():
        rs = [rows[k] for k in s["keys"] if k in rows]
        if not rs:
            continue
        w = [max(r.get("mcap_b") or 0, 0) for r in rs]
        w = w if sum(w) else [1] * len(rs)

        def avg(f):
            pts = [(wi, r[f]) for wi, r in zip(w, rs) if r.get(f) is not None]
            t = sum(p for p, _ in pts)
            return sum(p * v for p, v in pts) / t if t else None
        r21, r126, r252 = avg("r21"), avg("r126"), avg("r252")
        out[name] = {"mcap_b": round(sum(r.get("mcap_b") or 0 for r in rs), 1), "n": len(rs),
                     "mom_12_1": None if r252 is None or r21 is None else (1 + r252) / (1 + r21) - 1,
                     "mom_6_1": None if r126 is None or r21 is None else (1 + r126) / (1 + r21) - 1,
                     "above200": avg("above200"), "evs_pct_3y": avg("evs_pct3y"), "rev30": avg("rev30")}
    return out


def regime(c, macro):
    g = c["regime"]
    m = lambda k, f: (macro.get(k) or {}).get(f)
    flags = []
    ro, rn = g["risk_off"], g["risk_on"]
    if (m("vix", "last") or 0) >= ro["vix_min"] or (m("sp500", "dd") or 0) <= ro["sp500_dd_max"] or (m("hy", "d20") or 0) >= ro["hy_d20_min"]:
        flags.append("risk_off")
    elif (m("vix", "last") or 99) <= rn["vix_max"] and (m("sp500", "dd") or -1) >= rn["sp500_dd_min"]:
        flags.append("risk_on")
    d10 = m("us10y", "d20")
    if d10 is not None and d10 >= g["rates_up_d20"]:
        flags.append("rates_up")
    elif d10 is not None and d10 <= g["rates_down_d20"]:
        flags.append("rates_down")
    tilt = {}
    for f in flags:
        for s, v in (g["tilts"].get(f) or {}).items():
            tilt[s] = tilt.get(s, 0) + v
    return flags, tilt


def run():
    c = cfg()
    rows = (json.loads(IN.read_text(encoding="utf-8")) if IN.exists() else {"rows": {}})["rows"]
    agg = aggregate(c, rows)
    names = [n for n in c["sectors"] if n in agg]
    if len(names) < 4:
        raise SystemExit("섹터 재료 부족 — --code 0·1을 execute_code로 돌려 --put 먼저")
    macro = (json.loads((DIR / "market_latest.json").read_text(encoding="utf-8")) if (DIR / "market_latest.json").exists() else {}).get("macro") or {}
    flags, tilt = regime(c, macro)
    # 공분산·σ — 섹터 ETF 일봉
    px = risk.load_prices()
    series = {k: risk.returns(v) for k, v in px.items()}
    etf = [c["sectors"][n]["etf"] for n in names]
    ok = [e in series for e in etf]
    if not all(ok):
        raise SystemExit("섹터 ETF 일봉 없음: " + ", ".join(e for e, o in zip(etf, ok) if not o))
    al = c["allocation"]
    days, X = risk.aligned(series, etf, al["window"])
    Sd, delta = risk.shrunk_cov(X, al["halflife"])
    S = construct.mscale(Sd, 252)
    sig = [math.sqrt(S[i][i]) for i in range(len(names))]
    # 렌즈 z
    sub = {}
    for lens, L in c["lenses"].items():
        for sname in L["signals"]:
            if sname == "regime":
                sub[(lens, sname)] = {n: float(tilt.get(n, 0)) for n in names}
            else:
                vals = {n: agg[n].get(sname) for n in names}
                z = zs(vals)
                if sname == "evs_pct_3y":   # 백분위가 낮을수록 싸다 → 가치 +
                    z = {k: -v for k, v in z.items()}
                sub[(lens, sname)] = z
    lens_z = {lens: {n: sum(w * sub[(lens, s)][n] for s, w in L["signals"].items()) / sum(L["signals"].values()) for n in names} for lens, L in c["lenses"].items()}
    contrib = {lens: {n: c["lenses"][lens]["ic"] * sig[i] * lens_z[lens][n] for i, n in enumerate(names)} for lens in c["lenses"]}
    mu = {n: sum(contrib[l][n] for l in contrib) for n in names}
    # 블랙-리터만 — 벤치마크 = 바스켓 시총 비중
    tot = sum(agg[n]["mcap_b"] for n in names)
    bench = [agg[n]["mcap_b"] / tot for n in names]
    mk = series.get("AMEX:SPY") or {}
    betas = []
    for e in etf:
        dd = sorted(set(series[e]) & set(mk))[-al["window"]:]
        betas.append(risk.ols_beta([mk[d] for d in dd], [series[e][d] for d in dd]) if len(dd) > 20 else 1.0)
    bl_cfg = {"bl": {"tau": al["tau"], "mrp": al["mrp"], "lambda": al["lambda"]}}
    pi, post = construct.black_litterman(S, betas, {i: mu[n] for i, n in enumerate(names)}, {i: al["view_conf"] for i in range(len(names))}, bl_cfg)
    w = mvo(post, S, bench, al)
    out = {"as_of": datetime.now(KST).isoformat(timespec="seconds"), "data_as_of": (json.loads(IN.read_text(encoding="utf-8")) if IN.exists() else {}).get("as_of"),
           "regime": flags, "cov_days": len(days), "shrink_delta": round(delta, 3), "note": "연구용 모델 섹터 배분 지표 — 매매·비중 지시가 아님",
           "sectors": [{"sector": n, "etf": c["sectors"][n]["etf"], "bench": round(bench[i], 4), "model": round(w[i], 4), "active": round(w[i] - bench[i], 4),
                        "z": {l: round(lens_z[l][n], 2) for l in lens_z}, "contrib": {l: round(contrib[l][n], 4) for l in contrib}, "mu": round(mu[n], 4),
                        "prior": round(pi[i], 4), "posterior": round(post[i], 4), "vol": round(sig[i], 3),
                        "raw": {k: (None if v is None else round(v, 4)) for k, v in agg[n].items()}} for i, n in enumerate(names)]}
    out["sectors"].sort(key=lambda x: -x["active"])
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def mvo(mu, S, bench, al, iters=6000, step=0.02):
    """max w'μ − λ/2·w'Σw, |w − b| ≤ active_max, 0 ≤ w ≤ w_max, Σw = 1 — 투영 경사(상자 투영 뒤 합을 1로 맞추는 이분 탐색)"""
    n = len(mu)
    lo = [max(0.0, b - al["active_max"]) for b in bench]
    hi = [min(al["w_max"], b + al["active_max"]) for b in bench]
    w = list(bench)

    def project(v):
        a, b = -1.0, 1.0
        for _ in range(60):   # Σ clip(v + t) = 1 인 t
            t = (a + b) / 2
            s = sum(min(hi[i], max(lo[i], v[i] + t)) for i in range(n))
            a, b = (t, b) if s < 1 else (a, t)
        return [min(hi[i], max(lo[i], v[i] + (a + b) / 2)) for i in range(n)]
    for _ in range(iters):
        g = construct.mv(S, w)
        w = project([w[i] + step * (mu[i] - al["lambda"] * g[i]) for i in range(n)])
    return w


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--code" in argv:
        print(code(int(argv[argv.index("--code") + 1])))
    elif "--put" in argv:
        print(put(argv[argv.index("--put") + 1]), "종목")
    else:
        r = run()
        print(f"[섹터 배분] 국면 {r['regime'] or ['중립']} · 공분산 {r['cov_days']}일(축소 {r['shrink_delta']})")
        for s in r["sectors"]:
            print(f"  {s['sector']}: 모델 {s['model']:.1%} (벤치 {s['bench']:.1%}, {s['active']:+.1%}p) · 추세 {s['z']['trend']:+.2f} 가치 {s['z']['value']:+.2f} 알파 {s['z']['alpha']:+.2f} · μ {s['mu']:+.2%}")


if __name__ == "__main__":
    main(sys.argv[1:])
