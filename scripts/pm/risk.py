"""모델 포트폴리오 위험 엔진 1단계 (마스터 지시 2026-11-04 "1단계부터 구현", 설계 knowledge/methods/portfolio_management_design.md 2절 ③④⑤)

연구용 가상 포트폴리오의 위험 지표다 — 마스터 계좌의 매매·비중 지시가 아니고, 마스터 포지션 파일을 읽지 않는다.
  ③ 위험 모델  EWMA 공분산(반감기) + 레드와·울프 축소(Ledoit & Wolf 2004, 척도 항등 목표) · 시장 β · 테마 팩터 노출(잔차 대 잔차 β)
  ④ 기준선     A 역변동성 · A' 위험 기여 균등(ERC, Maillard·Roncalli·Teiletche 2010) · B 계층적 위험 균형(HRP, López de Prado 2016) · 동일 가중
  ⑤ 오버레이   포트 예상 변동성 → 변동성 목표 승수, 과거 모의 낙폭 → 낙폭 제어 승수(Grossman & Zhou 1993), CVaR, β, 테마 쏠림, 이벤트 창 할인 대상
설정 config/pm.yaml. 시세: knowledge/models/pm/prices.json {"NYSE:EROC": [["2026-06-10", 종가, 거래량], …]} — 모델이 TradingView 일봉을 한 번에 하나씩 받아 --put.
ETF는 중간선거 관측 파일(knowledge/models/midterm2026/ohlcv.json)에 있으면 같이 쓴다.
사용: py scripts/pm/risk.py --symbols        # 받아야 할 심볼
      py scripts/pm/risk.py --put <json>     # 시세 합치기
      py scripts/pm/risk.py                  # 계산 → knowledge/models/pm/latest.json
"""
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "knowledge" / "models" / "pm"
PRICES = DIR / "prices.json"
MID = ROOT / "knowledge" / "models" / "midterm2026" / "ohlcv.json"
KST = timezone(timedelta(hours=9))
EXCH = {"NYSE": "NYSE", "NASDAQ": "NASDAQ", "NYSE AMERICAN": "AMEX", "AMEX": "AMEX"}


def cfg():
    return yaml.safe_load((ROOT / "config" / "pm.yaml").read_text(encoding="utf-8"))


def universe(c=None):
    """(심볼, 티커, 상태) — 미국 상장 보유·관심 종목만(TradingView 거래소 표기를 알 수 있는 것)"""
    c = c or cfg()
    port = yaml.safe_load((ROOT / "config" / "portfolio.yaml").read_text(encoding="utf-8"))
    out = []
    for h in port.get("holdings") or []:
        ex = EXCH.get(str(h.get("exchange") or "").upper())
        if h.get("status") in c["universe"]["status"] and ex and h.get("ticker"):
            out.append((f"{ex}:{h['ticker']}", h["ticker"], h["status"]))
    return out


def factor_symbols(c=None):
    c = c or cfg()
    return [c["universe"]["market"]] + list(c["universe"]["themes"].values())


def load_prices():
    have = json.loads(PRICES.read_text(encoding="utf-8")) if PRICES.exists() else {}
    if MID.exists():   # ETF 일봉 재사용 [날짜, 시, 고, 저, 종, 거래량] → [날짜, 종, 거래량]
        for k, bars in json.loads(MID.read_text(encoding="utf-8")).items():
            m = {b[0]: b for b in have.get(k, [])}
            for b in bars:
                m.setdefault(b[0][:10], [b[0][:10], b[4], b[5]])
            have[k] = [m[d] for d in sorted(m)]
    return have


def put(path):
    new = json.loads(Path(path).read_text(encoding="utf-8"))
    have = json.loads(PRICES.read_text(encoding="utf-8")) if PRICES.exists() else {}
    for sym, bars in new.items():
        m = {b[0][:10]: b for b in have.get(sym, [])}
        for b in bars:   # [날짜, 종가, 거래량] 또는 TradingView [날짜, 시, 고, 저, 종, 거래량]
            m[b[0][:10]] = [b[0][:10], float(b[4]), float(b[5])] if len(b) >= 6 else [b[0][:10], float(b[1]), float(b[2]) if len(b) > 2 else 0.0]
        have[sym] = [m[d] for d in sorted(m)]
    DIR.mkdir(parents=True, exist_ok=True)
    PRICES.write_text(json.dumps(have), encoding="utf-8")
    return len(new)


def returns(bars):
    return {bars[i][0]: bars[i][1] / bars[i - 1][1] - 1 for i in range(1, len(bars)) if bars[i - 1][1]}


# ── ③ 위험 모델 ──────────────────────────────────────────────

def aligned(series, names, window):
    """공통 날짜의 수익률 행렬(행 = 날짜, 열 = names)"""
    days = sorted(set.intersection(*(set(series[n]) for n in names))) if names else []
    days = days[-window:]
    return days, [[series[n][d] for n in names] for d in days]


def ewma_cov(X, halflife):
    n, k = len(X), len(X[0])
    lam = 0.5 ** (1 / halflife)
    w = [lam ** (n - 1 - t) for t in range(n)]
    sw = sum(w)
    w = [x / sw for x in w]
    mu = [sum(w[t] * X[t][j] for t in range(n)) for j in range(k)]
    return [[sum(w[t] * (X[t][i] - mu[i]) * (X[t][j] - mu[j]) for t in range(n)) for j in range(k)] for i in range(k)]


def ledoit_wolf_delta(X):
    """Ledoit & Wolf(2004) 척도 항등 목표 F = m·I의 최적 축소 강도 δ ∈ [0, 1] — 동일 가중 표본에서 해석해"""
    n, k = len(X), len(X[0])
    mu = [sum(r[j] for r in X) / n for j in range(k)]
    Y = [[r[j] - mu[j] for j in range(k)] for r in X]
    S = [[sum(y[i] * y[j] for y in Y) / n for j in range(k)] for i in range(k)]
    m = sum(S[i][i] for i in range(k)) / k
    d2 = sum((S[i][j] - (m if i == j else 0.0)) ** 2 for i in range(k) for j in range(k)) / k
    b2 = sum(sum((y[i] * y[j] - S[i][j]) ** 2 for i in range(k) for j in range(k)) / k for y in Y) / n ** 2
    return min(b2, d2) / d2 if d2 else 1.0, m


def shrunk_cov(X, halflife):
    E = ewma_cov(X, halflife)
    delta, _ = ledoit_wolf_delta(X)
    k = len(E)
    m = sum(E[i][i] for i in range(k)) / k
    return [[(1 - delta) * E[i][j] + (delta * m if i == j else 0.0) for j in range(k)] for i in range(k)], delta


def ols_beta(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx if sxx else 0.0


def exposures(series, name, c, window):
    """시장 β와 테마 노출(종목의 SPY 잔차를 테마 ETF의 SPY 잔차에 회귀)"""
    mk = c["universe"]["market"]
    days = sorted(set(series[name]) & set(series.get(mk, {})))[-window:]
    if len(days) < c["risk"]["min_days"]:
        return None
    x, y = [series[mk][d] for d in days], [series[name][d] for d in days]
    b = ols_beta(x, y)
    out = {"beta": round(b, 2), "themes": {}}
    for th, sym in c["universe"]["themes"].items():
        dd = [d for d in days if d in series.get(sym, {})]
        if len(dd) < c["risk"]["min_days"]:
            continue
        xm = [series[mk][d] for d in dd]
        bt = ols_beta(xm, [series[sym][d] for d in dd])
        rt = [series[sym][d] - bt * series[mk][d] for d in dd]
        ri = [series[name][d] - b * series[mk][d] for d in dd]
        out["themes"][th] = round(ols_beta(rt, ri), 2)
    return out


# ── ④ 기준선 구성 ─────────────────────────────────────────────

def inv_vol(S):
    v = [1 / math.sqrt(S[i][i]) if S[i][i] > 0 else 0.0 for i in range(len(S))]
    s = sum(v)
    return [x / s for x in v]


def matvec(S, w):
    return [sum(S[i][j] * w[j] for j in range(len(w))) for i in range(len(w))]


def erc(S, iters=500, tol=1e-10):
    """위험 기여 균등: w_i·(Σw)_i가 모두 같게 — 고정점 반복(w_i ∝ 1/(Σw)_i)"""
    w = inv_vol(S)
    for _ in range(iters):
        m = matvec(S, w)
        new = [1 / m[i] if m[i] > 0 else 0.0 for i in range(len(w))]
        s = sum(new)
        new = [math.sqrt(a * b / s) for a, b in zip(w, new)]   # 기하 평균으로 진동을 줄인다
        s = sum(new)
        new = [x / s for x in new]
        if max(abs(a - b) for a, b in zip(new, w)) < tol:
            return new
        w = new
    return w


def corr(S):
    k = len(S)
    return [[S[i][j] / math.sqrt(S[i][i] * S[j][j]) if S[i][i] > 0 and S[j][j] > 0 else 0.0 for j in range(k)] for i in range(k)]


def hrp(S):
    """López de Prado(2016) — 상관 거리 단일 연결 군집 → 준대각 순서 → 재귀 이분(군집 분산의 역수로 나눔)"""
    k = len(S)
    if k == 1:
        return [1.0]
    C = corr(S)
    D = [[math.sqrt(max(0.0, (1 - C[i][j]) / 2)) for j in range(k)] for i in range(k)]
    clusters = {i: [i] for i in range(k)}
    while len(clusters) > 1:   # 단일 연결: 가장 가까운 두 군집을 합친다(순서 = 합친 순서대로 이어 붙임)
        keys = list(clusters)
        best = min(((a, b) for x, a in enumerate(keys) for b in keys[x + 1:]),
                   key=lambda ab: min(D[i][j] for i in clusters[ab[0]] for j in clusters[ab[1]]))
        a, b = best
        clusters[a] = clusters[a] + clusters.pop(b)
    order = next(iter(clusters.values()))
    w = [1.0] * k

    def cvar(idx):
        sub = [[S[i][j] for j in idx] for i in idx]
        iv = inv_vol(sub)
        return sum(iv[x] * sub[x][y] * iv[y] for x in range(len(idx)) for y in range(len(idx)))

    stack = [order]
    while stack:
        idx = stack.pop()
        if len(idx) < 2:
            continue
        h = len(idx) // 2
        L, R = idx[:h], idx[h:]
        vl, vr = cvar(L), cvar(R)
        a = 1 - vl / (vl + vr) if vl + vr else 0.5
        for i in L:
            w[i] *= a
        for i in R:
            w[i] *= 1 - a
        stack += [L, R]
    s = sum(w)
    return [x / s for x in w]


# ── ⑤ 오버레이 지표 ──────────────────────────────────────────

def port_stats(w, S, X, names, expo, c):
    ann = c["risk"]["annualize"]
    var = sum(w[i] * S[i][j] * w[j] for i in range(len(w)) for j in range(len(w)))
    vol = math.sqrt(var * ann)
    pr = [sum(wi * x for wi, x in zip(w, row)) for row in X]   # 과거 모의 일간 수익(지금 비중을 과거에 대입 — 낙관 편향 있음)
    eq, peak, mdd = 1.0, 1.0, 0.0
    for r in pr:
        eq *= 1 + r
        peak = max(peak, eq)
        mdd = max(mdd, 1 - eq / peak)
    dd_now = 1 - eq / peak
    q = c["overlay"]["cvar_q"]
    tail = sorted(pr)[:max(1, int(len(pr) * (1 - q)))]
    rc = [w[i] * matvec(S, w)[i] / var if var else 0 for i in range(len(w))]
    beta = sum(w[i] * (expo[n] or {}).get("beta", 1.0) for i, n in enumerate(names))
    themes = {}
    for i, n in enumerate(names):
        for th, v in ((expo[n] or {}).get("themes") or {}).items():
            themes[th] = themes.get(th, 0) + w[i] * v
    o = c["overlay"]
    return {"weights": {n: round(x, 4) for n, x in zip(names, w)}, "risk_contrib": {n: round(x, 3) for n, x in zip(names, rc)},
            "vol_ann": round(vol, 4), "cvar_1d": round(-sum(tail) / len(tail), 4), "max_dd": round(mdd, 4), "dd_now": round(dd_now, 4),
            "beta": round(beta, 2), "themes": {k: round(v, 2) for k, v in themes.items()},
            "vol_target_scale": round(min(1.0, o["sigma_target"] / vol), 3) if vol else 1.0,
            "dd_control_scale": round(max(0.0, 1 - dd_now / o["dd_max"]), 3),
            "over_w_max": [n for n, x in zip(names, w) if x > o["w_max"] + 1e-9]}


def events(c, today=None):
    """config/portfolio.yaml events 중 지금 이벤트 창에 든 것 → 비중 할인 대상"""
    today = today or datetime.now(KST).date()
    port = yaml.safe_load((ROOT / "config" / "portfolio.yaml").read_text(encoding="utf-8"))
    out = []
    for e in port.get("events") or []:
        try:
            d = date.fromisoformat(str(e.get("date")))
        except ValueError:
            continue
        what = str(e.get("what", ""))
        kind = "실적" if "실적" in what else "보호예수" if "보호예수" in what else "기타"
        a, b = c["overlay"]["event_window"][kind]
        if d + timedelta(days=a) <= today <= d + timedelta(days=b):
            out.append({"ticker": e.get("ticker"), "date": str(d), "kind": kind, "haircut": c["overlay"]["event_haircut"], "what": what[:60]})
    return out


def compute(c=None, today=None):
    c = c or cfg()
    px = load_prices()
    series = {k: returns(v) for k, v in px.items()}
    uni, short = [], []
    for sym, tk, st in universe(c):
        n = len(series.get(sym, {}))
        (uni if n >= c["risk"]["min_days"] else short).append(sym if n >= c["risk"]["min_days"] else {"symbol": sym, "days": n})
    expo = {s: exposures(series, s, c, c["risk"]["window"]) for s in uni}
    out = {"as_of": datetime.now(KST).isoformat(timespec="seconds"), "universe": uni, "short_history": short, "exposures": expo,
           "events": events(c, today), "note": "연구용 가상 포트폴리오 지표 — 매매·비중 지시가 아님"}
    if len(uni) >= 2:
        days, X = aligned(series, uni, c["risk"]["window"])
        if len(days) >= c["risk"]["min_days"]:
            S, delta = shrunk_cov(X, c["risk"]["halflife"])
            out.update({"days": len(days), "from": days[0], "to": days[-1], "shrink_delta": round(delta, 3),
                        "vol_ann": {n: round(math.sqrt(S[i][i] * c["risk"]["annualize"]), 3) for i, n in enumerate(uni)},
                        "corr": {n: {m: round(v, 2) for m, v in zip(uni, row)} for n, row in zip(uni, corr(S))}})
            k = len(uni)
            out["baselines"] = {name: port_stats(w, S, X, uni, expo, c)
                                for name, w in (("동일 가중", [1 / k] * k), ("역변동성", inv_vol(S)), ("위험 기여 균등", erc(S)), ("HRP", hrp(S)))}
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / "latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--symbols" in argv:
        have = load_prices()
        print(json.dumps({"stocks": [s for s, _, _ in universe()], "factors": factor_symbols(),
                          "missing": [s for s in [u for u, _, _ in universe()] + factor_symbols() if s not in have]}, ensure_ascii=False))
    elif "--put" in argv:
        print(put(argv[argv.index("--put") + 1]), "종목")
    else:
        r = compute()
        print(f"[PM 위험] 우주 {len(r['universe'])} · 이력 부족 {len(r['short_history'])} · 공통 {r.get('days', 0)}일 · 축소 δ {r.get('shrink_delta')}")
        for n, b in (r.get("baselines") or {}).items():
            print(f"  {n}: 변동성 {b['vol_ann']:.1%} · 최대낙폭 {b['max_dd']:.1%} · β {b['beta']} · 변동성목표 승수 {b['vol_target_scale']} · 낙폭 승수 {b['dd_control_scale']}")
        for e in r["events"]:
            print(f"  이벤트 창: {e['ticker']} {e['date']} {e['kind']} × {e['haircut']}")


if __name__ == "__main__":
    main(sys.argv[1:])
