"""INNIO(INIO) 동인 기반 DCF 모델 — 테스트(2026-10-28, 마스터 요청 '2Q 대비 3Q 콜 요인 정량화')

구조: 장비(인도 GW × $/kW × 마진) + 서비스(기존 설치 기반 44GW + 신규 인도분의 연령별 서비스 강도) − 본사비
→ 조정 EBITDA → EBIT(감가상각) → 세후 → FCFF(− CAPEX − 운전자본) → 2026~2035 할인 + 영구성장 → 주당가치.
단위: 금액 $B(10억 달러), 인도량 GW, 서비스 강도 $k/MW/년. 근거는 factors.yaml·README.md.
BASE = 2분기 콜(2026-07) 이후 정보 집합. factors.yaml이 3분기 콜(2026-10-27) 요인을 하나씩 덧씌운다.
"""

YEARS = list(range(2026, 2036))

BASE = {
    # 2026 실적 가이던스(2분기 시점): 매출 $3.8~3.9B, 조정 EBITDA $720~740M → 중간값
    "rev_2026": 3.85, "ebitda_2026": 0.73, "svc_2026": 1.35,   # 2분기: 장비 비중 ~65%
    # 인도량(GW): 2026 가이던스 + 캐파 3.5GW(2025) → 10GW+(2030) 확장 경로 × 가동률
    "gw": {2026: 4.5, 2027: 6.0, 2028: 7.3, 2029: 8.4, 2030: 9.3}, "g_gw_post": 0.02,
    "util_2029_2031": 0.90,           # 2029~2031 캐파 대비 수요 충족률(슬롯 가시성)
    "usd_per_kw": 560,                # 2027년 이후 장비 매출/kW(2026년 불변가), 연 물가 2%
    "price_infl": 0.02,
    "eq_margin": {2027: 0.165, 2028: 0.170},   # 장비 조정 EBITDA 마진(2분기: 연말 출구 'high teens'), 2030까지 유지 후 장기값으로
    "eq_margin_lr": 0.13,
    "g_svc_legacy": 0.07,             # 기존 설치 기반 서비스 성장(2027~2030, '고한자릿수'), 이후 4%
    "dc_share": 0.65,                 # 신규 인도분 중 데이터센터(상시 운전) 비중
    "svc_int_dc": 40.0,               # 신규 데이터센터 설치분 평생 평균 서비스 매출 $k/MW/년(2분기: '기존 평균보다 상당히 높다' — 수치 없음, 30과 미공시 상향의 중간)
    "svc_int_other": 30.0,
    "svc_margin_2026": 0.31, "svc_margin_2035": 0.33,
    "corp_cost_2026": 0.045, "corp_growth": 0.05,
    "da_pct": 0.035,
    "capex": {2026: 0.27, 2027: 0.35, 2028: 0.35, 2029: 0.30}, "capex_pct_post": 0.03,
    "nwc_pct": 0.08,                  # 매출 증가분 대비 운전자본(선수금으로 낮음)
    "tax": 0.25, "wacc": 0.100, "g_term": 0.03,
    "net_debt": 1.91,                 # 2분기 말 총차입 2.95(yfinance) − 현금 1.04(10-Q). 회사 정의 순차입(레버리지 배수 기준)보다 보수적
    "shares": 0.750,
}
# 신규 설치분의 연령별 서비스 강도(평생 평균=1 기준). 첫해 느리고 오버홀 연도에 높다(3분기 콜 p.24 설명 반영)
AGE_RAMP = [0.25, 0.45, 0.65, 0.85, 1.05, 1.15, 1.15, 1.2, 1.2, 1.25]


def _interp(d, y, default):
    keys = sorted(d)
    if y in d:
        return d[y]
    if y < keys[0]:
        return default
    if y > keys[-1]:
        return d[keys[-1]]
    lo = max(k for k in keys if k < y)
    hi = min(k for k in keys if k > y)
    return d[lo] + (d[hi] - d[lo]) * (y - lo) / (hi - lo)


def project(p):
    rows = []
    gw = {}
    for y in YEARS:
        if y <= 2030:
            g = p["gw"][y] * (p["util_2029_2031"] / 0.90 if y >= 2029 else 1.0)
        else:
            g = gw[y - 1] * (1 + p["g_gw_post"])
            if y == 2031:
                g *= p["util_2029_2031"] / 0.90
        gw[y] = g
    svc_legacy = p["svc_2026"]
    rev_prev = None
    for i, y in enumerate(YEARS):
        if y == 2026:
            svc = p["svc_2026"]
            eq_rev = p["rev_2026"] - svc
            ebitda = p["ebitda_2026"]
            corp = p["corp_cost_2026"]
            eq_m = (ebitda + corp - svc * p["svc_margin_2026"]) / eq_rev
        else:
            svc_legacy *= 1 + (p["g_svc_legacy"] if y <= 2030 else 0.04)
            infl = (1 + p["price_infl"]) ** (y - 2026)
            new = 0.0
            for j, yd in enumerate(YEARS):   # 2026년 이후 인도분이 이듬해부터 서비스 발생
                age = y - yd
                if 1 <= age <= len(AGE_RAMP):
                    mw = gw[yd] * 1000
                    intensity = p["dc_share"] * p["svc_int_dc"] + (1 - p["dc_share"]) * p["svc_int_other"]
                    new += mw * intensity * AGE_RAMP[age - 1] / 1e6   # $k × MW → $B
            svc = svc_legacy + new * infl
            eq_rev = gw[y] * p["usd_per_kw"] * infl / 1000           # GW × $/kW → $B
            if y <= 2028:
                eq_m = _interp(p["eq_margin"], y, p["eq_margin"][min(p["eq_margin"])])
            elif y <= 2030:
                eq_m = p["eq_margin"][max(p["eq_margin"])]
            else:
                hi = p["eq_margin"][max(p["eq_margin"])]
                eq_m = hi + (p["eq_margin_lr"] - hi) * min(1.0, (y - 2030) / 5)
            corp = p["corp_cost_2026"] * (1 + p["corp_growth"]) ** (y - 2026)
            svc_m = p["svc_margin_2026"] + (p["svc_margin_2035"] - p["svc_margin_2026"]) * (y - 2026) / 9
            ebitda = eq_rev * eq_m + svc * svc_m - corp
        rev = eq_rev + svc
        da = rev * p["da_pct"]
        ebit = ebitda - da
        capex = p["capex"].get(y, rev * p["capex_pct_post"])
        dnwc = 0.0 if rev_prev is None else (rev - rev_prev) * p["nwc_pct"]
        fcff = ebit * (1 - p["tax"]) + da - capex - dnwc
        rows.append({"year": y, "gw": gw[y], "eq_rev": eq_rev, "svc": svc, "rev": rev, "eq_m": eq_m,
                     "ebitda": ebitda, "ebit": ebit, "capex": capex, "fcff": fcff})
        rev_prev = rev
    return rows


def value(p):
    rows = project(p)
    w, g = p["wacc"], p["g_term"]
    pv = sum(r["fcff"] / (1 + w) ** (i + 0.75) for i, r in enumerate(rows))   # 2026년은 4분기만 남음 → 근사
    tv = rows[-1]["fcff"] * (1 + g) / (w - g)
    pv_tv = tv / (1 + w) ** (len(rows) - 0.25)
    ev = pv + pv_tv
    eq = ev - p["net_debt"]
    return {"ev": ev, "equity": eq, "per_share": eq / p["shares"], "tv_share": pv_tv / ev, "rows": rows}


if __name__ == "__main__":
    v = value(BASE)
    print(f"EV {v['ev']:.2f}B / 주당 {v['per_share']:.2f} / TV 비중 {v['tv_share']:.0%}")
    for r in v["rows"]:
        print(f"{r['year']} GW {r['gw']:.1f} 장비 {r['eq_rev']:.2f} 서비스 {r['svc']:.2f} 매출 {r['rev']:.2f} "
              f"장비마진 {r['eq_m']:.1%} EBITDA {r['ebitda']:.2f} FCFF {r['fcff']:.2f}")
