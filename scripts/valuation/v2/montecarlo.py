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


def within_factor(scens, sg):
    """1년차 성장 충격 축소 비율(ADR-041). σ_growth는 동인 생성기가 약세~강세 범위 ÷ 4로 잡는데, 시나리오를 확률로 섞는 단계에서 같은 범위가
    이미 들어간다 — 1년차 분산이 이중으로 커졌다(11/15 점검: 25·50·25 확률이면 총 σ가 의도의 1.7배). 시나리오 사이 분산을 빼고 남는 만큼만 쓴다:
    σ_within = √max(σ² − σ_between², (0.25σ)²) — 하한은 시나리오가 범위를 다 덮을 때도 잡음이 0이 되지 않게(사전값)"""
    starts = [(s.get("prob") or 0.0, s["growth"]["start"] if isinstance(s.get("growth"), dict) else (s.get("growth") or [0.0])[0]) for s in scens.values()]
    tot = sum(p for p, _ in starts)
    if not sg or tot <= 0:
        return 1.0
    mu = sum(p * g for p, g in starts) / tot
    var_b = sum(p * (g - mu) ** 2 for p, g in starts) / tot
    return math.sqrt(max(sg * sg - var_b, (0.25 * sg) ** 2)) / sg


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
    wf = within_factor(scens, sg)   # 1년차 충격은 시나리오 사이 분산을 뺀 만큼(ADR-041)
    v0, vh, used, dropped, picks = [], [], 0, 0, {}
    for _ in range(draws):
        name = _pick(rng, scens)
        sc = scens[name]
        d = scenarios.drivers(company, sc, wacc, g_term)
        if cc.get("enabled"):
            zg, zm = corr_pair(rng, float(cc.get("rho_growth_margin", 0.4)), cc.get("t_df"))
            first, shock = sg * wf * zg, sm * zm
        else:
            first, shock = 0.0, rng.gauss(0, sm)   # 상관 충격을 끄면 예전처럼 1년차 충격 없음
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
