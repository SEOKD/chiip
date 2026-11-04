"""모델 포트폴리오 구성 2단계 (마스터 지시 2026-11-04 "2단계 진행", 설계 knowledge/methods/portfolio_management_design.md 2절 ②④)

연구용 가상 포트폴리오다 — 마스터 계좌의 매매·비중 지시가 아니고, 마스터 포지션 파일을 읽지 않는다.
  ② 기대수익(1년)  세 식을 같이 계산하고 합친다. 부호가 엇갈리면 0으로 두고 '판단 충돌'
       PWR  확률 가중 수익 = p_bear·약세 + p_base·목표 + p_bull·강세 − 1 (리포트 verdict, scripts/discovery/buy_call.reports)
       α_G  그리놀드 알파 = IC × σ_잔차 × z(알파 잠재력 횡단면 z) (Grinold & Kahn 1999)
       E_c  컨빅션 기대값 = p·상방 − (1 − p)·하방, p = 그 종목 최근 Pulse 건의 방향 적중 확률(score_ledger conv_p) — 없으면 이 식은 빠진다
  ④ 블랙-리터만(Black & Litterman 1992; He & Litterman 1999; Idzorek 2005)
       사전 Π = β_i × 시장 위험 프리미엄(CAPM 균형 — 벤치마크가 시장일 때 λ·Σ·w_mkt와 같은 뜻, He & Litterman 1999).
         λ·Σ·w로 역산하면 변동성 60%대 종목의 내포 수익이 연 30~60%로 비현실적이라 CAPM으로 둔다(2026-11-04 첫 실행 점검)
       견해 Q = 합성 기대수익(리포트·알파가 있는 종목만), Ω_ii = (1/c − 1)·τ·Σ_ii, c = 견해 신뢰(컨빅션 있으면 2p − 1, 없으면 view_conf)
       사후 μ_BL → 제약 평균-분산: max w'μ − (λ/2)·w'Σw − κ·Σ|w − w_prev|, 0 ≤ w_i ≤ min(w_max, k_kelly·f*_i), 테마 군집 합 ≤ theme_max, Σw ≤ 1(나머지 현금)
       f*_i = 세 시나리오 분포의 단일 종목 켈리(무위험 rf). 투영 경사 상승(근사 해 — 소수 종목이라 충분)
  ⑤ 오버레이 적용  구성 비중 × min(변동성 목표 승수, 낙폭 제어 승수) × 이벤트 할인 → '오버레이 후 노출'
입력: knowledge/models/pm/latest.json(1단계 risk.py), 리포트, 알파, 성과 원장. 출력: knowledge/models/pm/construct.json
사용: py scripts/pm/risk.py && py scripts/pm/construct.py
"""
import csv
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "pm"))
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
import risk  # noqa: E402

DIR = ROOT / "knowledge" / "models" / "pm"
KST = timezone(timedelta(hours=9))


# ── 선형대수(표준 라이브러리) ─────────────────────────────────

def inv(A):
    n = len(A)
    M = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-18:
            raise ValueError("특이 행렬")
        M[c], M[p] = M[p], M[c]
        piv = M[c][c]
        M[c] = [x / piv for x in M[c]]
        for r in range(n):
            if r != c and M[r][c]:
                f = M[r][c]
                M[r] = [a - f * b for a, b in zip(M[r], M[c])]
    return [row[n:] for row in M]


def mv(A, x):
    return [sum(a * b for a, b in zip(row, x)) for row in A]


def madd(A, B):
    return [[a + b for a, b in zip(r, s)] for r, s in zip(A, B)]


def mscale(A, k):
    return [[a * k for a in r] for r in A]


# ── ② 기대수익 ───────────────────────────────────────────────

def kelly3(price, sc, probs, rf, steps=200):
    """세 시나리오(약세·기본·강세 가격)의 1년 단일 종목 켈리 f* ∈ [0, 1]"""
    rs = [p / price for p in sc]
    best_f, best_g = 0.0, -math.inf
    for i in range(steps + 1):
        f = i / steps
        g = sum(q * math.log(max(1e-12, (1 - f) * (1 + rf) + f * r)) for q, r in zip(probs, rs))
        if g > best_g + 1e-12:
            best_f, best_g = f, g
    return best_f


def conviction_p(ticker, path=ROOT / "knowledge" / "models" / "insight" / "score_ledger.csv", days=30):
    """그 종목 최근 Pulse 건의 방향 적중 확률과 방향(+1 유리 · −1 불리). 없으면 None"""
    if not path.exists():
        return None
    cut = (datetime.now(KST) - timedelta(days=days)).isoformat()
    with path.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if str(r.get("code", "")).upper() == ticker.upper() and r.get("conv_p") not in ("", None)
                and r.get("dir") not in ("", "0", None) and r.get("sent", "") >= cut]
    if not rows:
        return None
    r = rows[-1]
    return float(r["conv_p"]), int(float(r["dir"]))


def expected(rep, price, sigma_res, z, c):
    e = c["expected"]
    pb, pm, pu = e["scenario_probs"]
    out = {}
    if rep and price:
        sc = [rep["bear"], rep["target"], rep["bull"]]
        out["pwr"] = pb * sc[0] / price + pm * sc[1] / price + pu * sc[2] / price - 1 - e["rf"]   # 초과수익(무위험 차감) — CAPM 사전값과 같은 단위
        out["kelly"] = kelly3(price, sc, (pb, pm, pu), e["rf"])
        up, down = rep["bull"] / price - 1, 1 - rep["bear"] / price
        cp = conviction_p(rep["ticker"])
        if cp:
            p, d = cp
            out["conv"] = ((p * up - (1 - p) * down) if d > 0 else -(p * down - (1 - p) * up)) - e["rf"]
            out["conv_p"] = p
    if z is not None and sigma_res:
        out["grinold"] = e["ic"] * sigma_res * z
    parts = {k: out[k] for k in ("pwr", "grinold", "conv") if k in out}
    if not parts:
        return None, out
    signs = {math.copysign(1, v) for v in parts.values() if abs(v) > 1e-9}
    if len(signs) > 1:
        out["conflict"] = True
        return 0.0, out
    w = {k: e["weights"][k] for k in parts}
    s = sum(w.values())
    return sum(w[k] / s * parts[k] for k in parts), out


# ── ④ 블랙-리터만 + 제약 최적화 ──────────────────────────────

def black_litterman(S, betas, views, conf, c):
    """S 연율 공분산, betas 시장 β, views {i: Q_i}, conf {i: c_i} → (사전, 사후 기대수익)"""
    b = c["bl"]
    tau = b["tau"]
    pi = [bt * b["mrp"] for bt in betas]
    if not views:
        return pi, pi
    n = len(S)
    tS_inv = inv(mscale(S, tau))
    A = [row[:] for row in tS_inv]
    rhs = mv(tS_inv, pi)
    for i, q in views.items():
        ci = min(max(conf[i], 0.05), 0.95)
        om = (1 / ci - 1) * tau * S[i][i]
        A[i][i] += 1 / om
        rhs[i] += q / om
    return pi, mv(inv(A), rhs)


def optimize(mu, S, caps, groups, c, w_prev=None, iters=4000):
    """투영 경사 상승. caps = 종목 상한, groups = {군집: [i…]}"""
    o = c["opt"]
    lam, kappa, step = c["bl"]["lambda"], o["kappa"], o["step"]
    n = len(mu)
    w_prev = w_prev or [0.0] * n
    w = [min(caps[i], 1 / n) for i in range(n)]
    for _ in range(iters):
        g = mv(S, w)
        grad = [mu[i] - lam * g[i] - kappa * math.copysign(1, w[i] - w_prev[i]) * (abs(w[i] - w_prev[i]) > 1e-6) for i in range(n)]
        w = [min(max(w[i] + step * grad[i], 0.0), caps[i]) for i in range(n)]
        for idx in groups.values():
            s = sum(w[i] for i in idx)
            if s > c["overlay"]["theme_max"]:
                w = [w[i] * c["overlay"]["theme_max"] / s if i in idx else w[i] for i in range(n)]
        s = sum(w)
        if s > 1:
            w = [x / s for x in w]
    return w


def theme_groups(names, expo):
    """종목을 가장 큰 테마 노출의 군집으로"""
    g = {}
    for i, n in enumerate(names):
        th = (expo.get(n) or {}).get("themes") or {}
        key = max(th, key=th.get) if th else "기타"
        g.setdefault(key, []).append(i)
    return g


def run():
    c = yaml.safe_load((ROOT / "config" / "pm.yaml").read_text(encoding="utf-8"))
    rk = json.loads((DIR / "latest.json").read_text(encoding="utf-8"))
    names = rk["universe"]
    if len(names) < 2 or "baselines" not in rk:
        raise SystemExit("1단계 위험 결과가 없다 — py scripts/pm/risk.py 먼저")
    px = risk.load_prices()
    series = {k: risk.returns(v) for k, v in px.items()}
    _, X = risk.aligned(series, names, c["risk"]["window"])
    Sd, _ = risk.shrunk_cov(X, c["risk"]["halflife"])
    ann = c["risk"]["annualize"]
    S = mscale(Sd, ann)
    import buy_call
    reps = {r["ticker"].upper(): r for r in buy_call.reports().values()}
    alphas = json.loads((ROOT / "knowledge" / "models" / "alpha" / "latest.json").read_text(encoding="utf-8")).get("rows") or {}
    port = yaml.safe_load((ROOT / "config" / "portfolio.yaml").read_text(encoding="utf-8"))
    tk2id = {h["ticker"].upper(): h["id"] for h in port.get("holdings") or []}
    allz = [v.get("total") for v in alphas.values() if v.get("total") is not None]
    m0 = sum(allz) / len(allz)
    s0 = math.sqrt(sum((x - m0) ** 2 for x in allz) / (len(allz) - 1))
    mk = risk.returns(px[c["universe"]["market"]])
    md = sorted(mk)[-c["risk"]["window"]:]
    mm = sum(mk[d] for d in md) / len(md)
    var_m = sum((mk[d] - mm) ** 2 for d in md) / (len(md) - 1) * ann
    rows, views, conf, caps, betas = {}, {}, {}, [], []
    for i, sym in enumerate(names):
        tk = sym.split(":")[1].upper()
        price = px[sym][-1][1]
        b = (rk["exposures"].get(sym) or {}).get("beta", 1.0)
        sig_res = math.sqrt(max(S[i][i] - b * b * var_m, 0.25 * S[i][i]))   # 잔차 변동성 = 총 분산 − β²·시장 분산(하한: 총 분산의 1/4)
        a = (alphas.get(tk2id.get(tk, "")) or {}).get("total")
        z = (a - m0) / s0 if a is not None and s0 else None
        betas.append(b)
        mu, parts = expected(reps.get(tk), price, sig_res, z, c)
        k = parts.get("kelly")
        caps.append(min(c["overlay"]["w_max"], c["expected"]["k_kelly"] * k) if k is not None else c["overlay"]["w_max"])
        if mu is not None:
            views[i] = mu
            conf[i] = (2 * parts["conv_p"] - 1) if "conv_p" in parts else c["bl"]["view_conf"]
        rows[sym] = {"price": price, "alpha": a, "z": round(z, 2) if z is not None else None, "mu": None if mu is None else round(mu, 4),
                     **{k2: round(v, 4) if isinstance(v, float) else v for k2, v in parts.items()}, "report": (reps.get(tk) or {}).get("date")}
    k = len(names)
    pi, mu_bl = black_litterman(S, betas, views, conf, c)
    groups = theme_groups(names, rk["exposures"])
    w = optimize(mu_bl, S, caps, groups, c)
    base = rk["baselines"]["HRP"]
    scale = min(base["vol_target_scale"], base["dd_control_scale"])
    ev = {e["ticker"].upper(): e["haircut"] for e in rk.get("events") or []}
    final = [w[i] * scale * ev.get(names[i].split(":")[1].upper(), 1.0) for i in range(k)]
    vol = math.sqrt(sum(w[i] * S[i][j] * w[j] for i in range(k) for j in range(k)))
    for i, sym in enumerate(names):
        rows[sym].update({"pi": round(pi[i], 4), "mu_bl": round(mu_bl[i], 4), "cap": round(caps[i], 4), "w": round(w[i], 4), "w_overlay": round(final[i], 4)})
    out = {"as_of": datetime.now(KST).isoformat(timespec="seconds"), "rows": rows, "groups": {g: [names[i] for i in idx] for g, idx in groups.items()},
           "invested": round(sum(w), 4), "cash": round(1 - sum(w), 4), "vol_ann": round(vol, 4), "exp_return": round(sum(a * b for a, b in zip(w, mu_bl)), 4),
           "overlay_scale": round(scale, 3), "invested_after_overlay": round(sum(final), 4),
           "conflicts": [s for s, r in rows.items() if r.get("conflict")], "no_view": [s for s in names if s not in [names[i] for i in views]],
           "note": "연구용 가상 포트폴리오 지표 — 매매·비중 지시가 아님"}
    (DIR / "construct.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    day = max(px[n][-1][0] for n in names)   # 점수 이력(4단계 실현 IC 재료) — 같은 시세일은 한 줄
    hist = DIR / "score_hist.jsonl"
    seen = {json.loads(l)["date"] for l in hist.read_text(encoding="utf-8").splitlines() if l.strip()} if hist.exists() else set()
    if day not in seen:
        with hist.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"date": day, "mu": {s: r["mu"] for s, r in rows.items() if r["mu"] is not None},
                                "mu_bl": {s: r["mu_bl"] for s, r in rows.items()}}, ensure_ascii=False) + "\n")
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    r = run()
    print(f"[PM 구성] 투자 {r['invested']:.0%} · 현금 {r['cash']:.0%} · 예상 변동성 {r['vol_ann']:.1%} · 사후 기대수익 {r['exp_return']:+.1%} · 오버레이 승수 {r['overlay_scale']} → 노출 {r['invested_after_overlay']:.0%}")
    for s, x in r["rows"].items():
        print(f"  {s}: μ {x['mu']} · BL {x['mu_bl']:+.3f} · 상한 {x['cap']:.1%} · 구성 {x['w']:.1%} · 오버레이 후 {x['w_overlay']:.1%}" + (" · 판단 충돌" if x.get("conflict") else ""))


if __name__ == "__main__":
    main(sys.argv[1:])
