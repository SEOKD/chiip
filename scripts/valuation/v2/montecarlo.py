"""M4 확률 엔진 — 시나리오 혼합 + Schwartz·Moon형 확률 성장 경로 몬테카를로 (표준 라이브러리)

한 회 추출: ① 시나리오를 확률로 고름 ② 성장 경로를 평균회귀 확률과정으로 생성
  gₜ₊₁ = ḡ + (gₜ − ḡ)·decay + σ_g·ε   (decay = e^(−κ), ḡ = 시나리오 장기 성장)
③ 마진 경로에 수준 충격(σ_m), 재투자 효율에 로그정규 충격(σ_s2c), WACC에 정규 충격(σ_w)
④ 지금 지분가치와 h년 뒤 지분가치를 계산. WACC ≤ g이거나 수치 오류인 회는 버리고 개수를 보고한다.
목록형 성장(경기순환 시나리오)은 연도별 성장에 σ_g 잡음만 더한다.
D4(ADR-016, config/valuation_v3.yaml mc_corr): 1년차 성장 충격과 마진 수준 충격을 상관 ρ로 묶고(영업 레버리지),
두 충격을 분산 1로 맞춘 스튜던트 t(자유도 5)에서 뽑는다(두꺼운 꼬리). 성장 경로에는 D2 외부 관점 혼합을 다시 적용한다.
"""
import copy
import math
import random

import dcf
import plus
import scenarios


def t_unit(rng, df):
    """분산 1 스튜던트 t(df > 2). df가 없으면 표준정규"""
    if not df:
        return rng.gauss(0, 1)
    z = rng.gauss(0, 1)
    chi = sum(rng.gauss(0, 1) ** 2 for _ in range(int(df)))
    return z / math.sqrt(chi / df) * math.sqrt((df - 2) / df)


def corr_pair(rng, rho, df):
    """상관 rho인 분산 1 충격 두 개"""
    a, b = t_unit(rng, df), t_unit(rng, df)
    return a, rho * a + math.sqrt(1 - rho * rho) * b


def _pick(rng, scens):
    names = list(scens)
    probs = [scens[n].get("prob", 1 / len(names)) for n in names]
    x, acc = rng.random() * sum(probs), 0.0
    for n, p in zip(names, probs):
        acc += p
        if x <= acc:
            return n
    return names[-1]


def _growth_draw(rng, spec, n, sg, first=0.0):
    """first = 1년차 공통 충격(D4, σ_g 단위로 이미 곱한 값) — 평균회귀 경로는 이후 해에도 decay로 이어진다"""
    if isinstance(spec, list):
        base = scenarios.growth_path(spec, n)
        return [g + rng.gauss(0, sg) + (first if i == 0 else 0.0) for i, g in enumerate(base)]
    g, e, k = spec["start"] + first, spec["end"], spec.get("decay", 0.7)
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
    pc = plus.cfg() if company.get("plus", True) else {}
    cc = pc.get("mc_corr") or {}
    if company.get("plus", True):   # 경기순환 업종은 피어 마진 이동평균의 흔들림만큼 마진 충격을 넓힌다(2026-11-13 SK하이닉스 −30% 확률 0%)
        sm = plus.margin_sigma(company, sm, pc)
    med = scenarios._median(company) if company.get("plus", True) else None
    v0, vh, used, dropped, picks = [], [], 0, 0, {}
    for _ in range(draws):
        name = _pick(rng, scens)
        sc = scens[name]
        d = scenarios.drivers(company, sc, wacc, g_term)
        if cc.get("enabled"):
            zg, zm = corr_pair(rng, float(cc.get("rho_growth_margin", 0.4)), cc.get("t_df"))
            first, shock = sg * zg, sm * zm
        else:
            first, shock = 0.0, rng.gauss(0, sm)
        d["growth"] = [max(-0.9, g) for g in plus.outside_view(_growth_draw(rng, sc["growth"], n, sg, first), med, pc)]
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
