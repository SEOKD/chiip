"""M8 상승여력 블록 + 알파 4요소 정량 제안 (마스터 결정: 목표주가 대신 분포·확률·필요 가정)

입력: 몬테카를로 결과, 기본 시나리오 동인, 시가총액, 기저율.
출력(모두 시가총액 대비):
  지금 내재가치 분포(P10·P50·P90·기대값), h년 뒤 가치가 k배 이상일 확률, 30% 이상 고평가 확률, 비대칭,
  시장 내포 매출 CAGR과 그 기저율 백분위, 우리 기본 시나리오 CAGR 백분위, 2배·10배에 필요한 CAGR과 백분위.
알파 제안: upside ← P(h년 뒤 ≥2배) / gap ← 기저율 백분위 차(기본 − 내포) / asymmetry ← 비대칭.
bottleneck은 판단 요소라 여기서 만들지 않는다.
"""
import math

import baserates
import montecarlo
import pie


def block(company, base_d, mc, mcap, cfg_up, sample=None, years=5):
    v0 = [v / mcap for v in mc["v0"]]
    vh = [v / mcap for v in mc["vh"]]
    out = {"n": mc["used"], "dropped": mc["dropped"], "picks": mc["picks"]}
    if not v0:
        return out
    out.update({"v0_p10": montecarlo.quantile(v0, 0.1), "v0_p50": montecarlo.quantile(v0, 0.5),
                "v0_p90": montecarlo.quantile(v0, 0.9), "v0_mean": sum(v0) / len(v0),
                "p_over_30pct_overvalued": sum(1 for x in v0 if x < 0.7) / len(v0)})
    out["p_h"] = {k: sum(1 for x in vh if x >= k) / len(vh) for k in cfg_up.get("multiples", [1.5, 2, 3, 10])}
    up = sum(max(x - 1, 0) for x in vh) / len(vh)
    dn = sum(max(1 - x, 0) for x in vh) / len(vh)
    out["asymmetry"] = up / dn if dn > 0 else float("inf")
    start_rev = company["rev0"] * float(company.get("unit_usd", 1e9))
    out["base_cagr"] = pie.cagr(base_d, years)
    out["base_pct"] = baserates.percentile(out["base_cagr"], start_rev, years, sample=sample)
    k, ic = pie.implied_growth(base_d, mcap, 0, years)
    out["implied_cagr"] = ic
    out["implied_pct"] = baserates.percentile(ic, start_rev, years, sample=sample) if ic is not None else (None, 0, "", "역산 불가")
    out["required"] = {}
    for mult in (2, 10):
        _, rc = pie.implied_growth(base_d, mult * mcap, years, years)
        out["required"][mult] = (rc, baserates.percentile(rc, start_rev, years, sample=sample) if rc is not None else (None, 0, "", "역산 불가"))
    out["alpha"] = alpha_suggest(out, cfg_up)
    return out


def alpha_suggest(b, cfg_up):
    s = {}
    p2 = b["p_h"].get(2)
    if p2 is not None:
        s["upside"] = round(min(10.0, 10.0 * p2 / cfg_up.get("upside_full_prob", 0.5)), 1)
    a = b.get("asymmetry")
    if a is not None and a > 0:
        a = min(a, 64.0)
        s["asymmetry"] = round(max(0.0, min(10.0, 5 + cfg_up.get("asym_points_per_doubling", 2.5) * math.log2(a))), 1)
    bp, ip = (b.get("base_pct") or (None,))[0], (b.get("implied_pct") or (None,))[0]
    if bp is not None and ip is not None:
        s["gap"] = round(max(0.0, min(10.0, 5 + cfg_up.get("gap_points_per_10pct", 1.0) * (bp - ip) / 10)), 1)
    return s
