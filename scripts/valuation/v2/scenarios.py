"""시나리오 사양 → dcf 동인(dict) 변환. 종목별 drivers.yaml의 scenarios 블록을 해석한다

growth: [g1..gN] 목록, 또는 {start, end, decay}  — gₜ = end + (start − end)·decay^(t−1)
margin: [m1..mN] 목록, 또는 {m0, target, year_target, lr, lam}  — dcf.margin_path
ADR-016 보강(config/valuation_v3.yaml): D2 3년차 이후 성장을 기저율 중앙값 쪽으로 · D3 cyclical이면 마지막 해들 마진을 사이클 평균으로 ·
D6 ronic_spread가 없고 moat_score가 있으면 RONIC = WACC + max_spread × 해자. 끄려면 company['plus'] = False
"""
import dcf
import plus

_MEDIAN = {}


def _median(company):
    """규모 구간 기저율 5년 CAGR 중앙값(프로세스 안에서 한 번만 표본을 읽는다)"""
    start = company["rev0"] * float(company.get("unit_usd", 1e9))
    if "sample" not in _MEDIAN:
        import baserates
        _MEDIAN["sample"] = baserates.windows(5)
    return plus.base_median(start, _MEDIAN["sample"]) if _MEDIAN["sample"] else None


def growth_path(spec, n):
    if isinstance(spec, list):
        return (spec + [spec[-1]] * n)[:n]
    s, e, k = spec["start"], spec["end"], spec.get("decay", 0.7)
    return [e + (s - e) * k ** t for t in range(n)]


def margin_spec_path(spec, n):
    """anchors(1·2…년차 컨센서스 이익률)가 있으면 그 해들은 그대로 쓰고, 마지막 앵커 → target(year_target년차)로 잇는다.
    2026-10-29 CBRS 점검: 목표 이익률만 덮어쓰자 1년차(FY2027) 이익률이 컨센서스 +3% 대신 −36%가 되어 가치가 낮게 나왔다"""
    if isinstance(spec, list):
        return (spec + [spec[-1]] * n)[:n]
    anchors = list(spec.get("anchors") or [])[:n]
    if not anchors:
        return dcf.margin_path(spec["m0"], spec["target"], spec.get("year_target", 3), n, spec.get("lr"), spec.get("lam", 0.0))
    k, yt = len(anchors), max(spec.get("year_target", 3), len(anchors) + 1)
    rest = dcf.margin_path(anchors[-1], spec["target"], yt - k, n - k, spec.get("lr"), spec.get("lam", 0.0)) if n > k else []
    return anchors + rest


def drivers(company, scen, wacc, g_term):
    n = company.get("horizon", 10)
    m = company["market"]
    growth, margin, ronic = growth_path(scen["growth"], n), margin_spec_path(scen["margin"], n), (wacc + company["ronic_spread"]) if company.get("ronic_spread") else None
    if company.get("plus", True):
        c = plus.cfg()
        growth = plus.outside_view(growth, _median(company), c)
        margin = plus.normalize(margin, plus.normal_margin(plus.cyclical_spec(company, c))[0], c)
        ronic = plus.moat_ronic(wacc, company, c)
    return {"rev0": company["rev0"], "growth": growth, "margin": margin,
            "tax": company["tax"], "s2c": scen.get("s2c", company.get("s2c")), "ic0": company["ic0"], "wacc": wacc,
            "g_term": scen.get("g_term", g_term), "ronic": ronic, "net_debt": m["net_debt"], "shares": m["shares"],
            "nonop": company.get("nonop", 0.0), "minority": company.get("minority", 0.0),
            "midyear": company.get("midyear", True),
            "kd": company.get("kd", 0.05 * (1 - company["tax"]))}   # 순차입·순현금의 세후 이자(미 10년 5% 근사) — equity_at에서 사용
