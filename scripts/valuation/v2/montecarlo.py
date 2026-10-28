"""M4 확률 엔진 — 시나리오 혼합 + Schwartz·Moon형 확률 성장 경로 몬테카를로 (표준 라이브러리)

한 회 추출: ① 시나리오를 확률로 고름 ② 성장 경로를 평균회귀 확률과정으로 생성
  gₜ₊₁ = ḡ + (gₜ − ḡ)·decay + σ_g·ε   (decay = e^(−κ), ḡ = 시나리오 장기 성장)
③ 마진 경로에 수준 충격(σ_m), 재투자 효율에 로그정규 충격(σ_s2c), WACC에 정규 충격(σ_w)
④ 지금 지분가치와 h년 뒤 지분가치를 계산. WACC ≤ g이거나 수치 오류인 회는 버리고 개수를 보고한다.
목록형 성장(경기순환 시나리오)은 연도별 성장에 σ_g 잡음만 더한다.
"""
import copy
import math
import random

import dcf
import scenarios


def _pick(rng, scens):
    names = list(scens)
    probs = [scens[n].get("prob", 1 / len(names)) for n in names]
    x, acc = rng.random() * sum(probs), 0.0
    for n, p in zip(names, probs):
        acc += p
        if x <= acc:
            return n
    return names[-1]


def _growth_draw(rng, spec, n, sg):
    if isinstance(spec, list):
        base = scenarios.growth_path(spec, n)
        return [g + rng.gauss(0, sg) for g in base]
    g, e, k = spec["start"], spec["end"], spec.get("decay", 0.7)
    out = []
    for _ in range(n):
        out.append(g)
        g = e + (g - e) * k + rng.gauss(0, sg)
    return out


def simulate(company, wacc, g_term, horizon_year=5, draws=5000, seed=1):
    rng = random.Random(seed)
    mc = company.get("mc", {})
    sg, sm, ss, sw = mc.get("sigma_growth", 0.04), mc.get("sigma_margin", 0.02), mc.get("sigma_s2c", 0.2), mc.get("sigma_wacc", 0.005)
    scens = company["scenarios"]
    n = company.get("horizon", 10)
    v0, vh, used, dropped, picks = [], [], 0, 0, {}
    for _ in range(draws):
        name = _pick(rng, scens)
        sc = scens[name]
        d = scenarios.drivers(company, sc, wacc, g_term)
        d["growth"] = [max(-0.9, g) for g in _growth_draw(rng, sc["growth"], n, sg)]
        shock = rng.gauss(0, sm)
        d["margin"] = [m + shock for m in d["margin"]]
        d["s2c"] = max(0.2, d["s2c"] * math.exp(rng.gauss(0, ss)))
        d["wacc"] = wacc + rng.gauss(0, sw)
        try:
            if d["wacc"] <= d["g_term"] + 0.01:
                raise ValueError
            a = dcf.value(d)["equity"]
            b = dcf.equity_at(d, horizon_year)
        except (ValueError, ZeroDivisionError, OverflowError):
            dropped += 1
            continue
        v0.append(a)
        vh.append(b)
        picks[name] = picks.get(name, 0) + 1
        used += 1
    return {"v0": v0, "vh": vh, "used": used, "dropped": dropped, "picks": picks, "seed": seed}


def quantile(xs, q):
    s = sorted(xs)
    if not s:
        return None
    i = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return s[i]
