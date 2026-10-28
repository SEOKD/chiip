"""M3 할인율 — 바텀업 베타·국가위험·WACC (McKinsey·Damodaran 방식)

자기자본비용 = 무위험금리 + 재부채화 베타 × 내재 ERP + Σ(지역 매출 비중 × 국가위험)
베타: Damodaran 업종 베타(부채 포함)를 업종 평균 부채비율로 무부채화 → 회사 부채비율로 재부채화.
"""


def unlever(beta_l, equity_weight, tax):
    de = (1 - equity_weight) / equity_weight
    return beta_l / (1 + (1 - tax) * de)


def relever(beta_u, de, tax):
    return beta_u * (1 + (1 - tax) * de)


def cost_of_capital(regime, industry, region_mix, market_cap, net_debt, tax, pretax_kd=None, kd_spread=0.015):
    """dict(ke, kd, wacc, beta, crp, rf, erp). net_debt가 음수(순현금)면 부채비중 0으로 본다"""
    ind = regime["industry"][industry]
    rf, erp = regime["rf_us"], regime["erp"]
    bu = unlever(ind["beta"], ind["equity_weight"], tax)
    debt = max(net_debt, 0.0)
    de = debt / market_cap if market_cap > 0 else 0.0
    beta = relever(bu, de, tax)
    crp = sum(w * regime["crp"].get(r, 0.0) for r, w in region_mix.items())
    ke = rf + beta * erp + crp
    kd = pretax_kd if pretax_kd is not None else rf + kd_spread
    wd = debt / (debt + market_cap) if (debt + market_cap) > 0 else 0.0
    wacc = (1 - wd) * ke + wd * kd * (1 - tax)
    return {"ke": ke, "kd": kd, "wacc": wacc, "beta": beta, "beta_unlevered": bu, "crp": crp, "rf": rf, "erp": erp, "debt_weight": wd}
