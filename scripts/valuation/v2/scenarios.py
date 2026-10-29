"""시나리오 사양 → dcf 동인(dict) 변환. 종목별 drivers.yaml의 scenarios 블록을 해석한다

growth: [g1..gN] 목록, 또는 {start, end, decay}  — gₜ = end + (start − end)·decay^(t−1)
margin: [m1..mN] 목록, 또는 {m0, target, year_target, lr, lam}  — dcf.margin_path
"""
import dcf


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
    return {"rev0": company["rev0"], "growth": growth_path(scen["growth"], n), "margin": margin_spec_path(scen["margin"], n),
            "tax": company["tax"], "s2c": scen.get("s2c", company.get("s2c")), "ic0": company["ic0"], "wacc": wacc,
            "g_term": scen.get("g_term", g_term), "ronic": (wacc + company["ronic_spread"]) if company.get("ronic_spread") else None, "net_debt": m["net_debt"], "shares": m["shares"],
            "nonop": company.get("nonop", 0.0), "minority": company.get("minority", 0.0),
            "midyear": company.get("midyear", True),
            "kd": company.get("kd", 0.05 * (1 - company["tax"]))}   # 순차입·순현금의 세후 이자(미 10년 5% 근사) — equity_at에서 사용
