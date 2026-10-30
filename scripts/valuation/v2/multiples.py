"""멀티플 엔진 — 과거 레인지 → 동종 레인지 → 펀더멘털 내재 멀티플(ROIC·성장·이익률) → 할인·프리미엄 분해 → 합리적 멀티플
(마스터 지시 2026-10-29 "멀티플 산정은 과거 레인지 참조를 넘어 주요 동종업계 레인지를 비교하고, 멀티플 할인이 시장 예상대로 적용됐는지
파악하고, ROIC 등 핵심 실적 지표에 비례해 멀티플을 합리적으로 산정하라. 맥킨지 밸류에이션이나 최신 기법 논문을 참고").

방법(knowledge/methods/multiples.md에 문헌·한계):
  1) 자기 과거 레인지 — datapack history.ev_sales(날짜별) 분위.
  2) 동종 레인지 — 같은 기준(peers_basis)의 EV/매출 25·50·75분위와 대상의 위치.
  3) 펀더멘털 내재 멀티플(McKinsey 가치 동인) — 회사마다 같은 WACC·계속가치 규칙(RONIC = WACC)으로 자기 성장 경로·이익률·
     자본 회전율(매출÷투하자본 = ROIC ÷ 세후 이익률)을 자본화한 EV ÷ 매출. 동종은 '현재 수익성 유지 + 성장 감속', 대상은 v2 기본 시나리오.
  4) 시장 ÷ 내재 = 섹터 심리 배율(동종 중앙값) — 시장이 펀더멘털 이상으로 얹어 주는 몫.
  5) 분해(Rhodes-Kropf·Robinson·Viswanathan 2005의 정신): ln(대상 시장 배수 ÷ 동종 중앙 시장 배수)
       = ln(대상 내재 ÷ 동종 중앙 내재)  [펀더멘털 차이로 정당한 할인·프리미엄]
       + ln(섹터 심리 배율)이 대상에 똑같이 적용됐다고 볼 때의 나머지 [기업 고유 — 시장이 따로 얹은 기대 또는 할인]
  6) 합리적 멀티플 = 대상 내재 × 동종 심리 배율(중앙, 25~75분위 범위) → 가치 ÷ 시가총액.
  7) ROIC 비례 표 — 정상 상태 EV/NOPAT = (1 − g/ROIC)/(WACC − g), EV/매출 = 그 × 세후 영업이익률.
"""
import math

import dcf
import scenarios


def pct(xs, q):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def peer_fundamentals(p, tax=0.21):
    """동종 1곳 → (ROIC 영업권 포함, ROIC 영업권 제외, 매출÷투하자본(영업권 제외), 투하자본(영업권 제외)).
    투하자본 = 자기자본(시가총액 ÷ PBR) + 차입 − 현금. 맥킨지: 영업권 포함 ROIC는 인수 대가까지 낸 주주의 수익률, 영업권 제외 ROIC가
    사업 자체의 경제성이자 새 투자 수익률(RONIC)의 근거 — 2026-10-29 CBRS 점검에서 AMD(자일링스)·MRVL(인파이) 영업권 때문에 내재 멀티플이 음수가 됐다"""
    eq = p["mcap"] / p["pb"] if p.get("pb") else None
    ic = (eq or 0) + (p.get("debt") or 0) - (p.get("cash") or 0) if eq else None
    if not ic or ic <= 0:
        return None, None, None, ic
    ic_ex = ic - (p.get("goodwill") or 0) - (p.get("intangibles") or 0)
    nopat = p["rev"] * p["ebit_margin"] * (1 - tax)
    if ic_ex <= 0:
        ic_ex = None
    return nopat / ic, (nopat / ic_ex if ic_ex else None), (p["rev"] / ic_ex if ic_ex else p["rev"] / ic), (ic_ex or ic)


def warranted_ev_sales(rev, growth, margin, s2c, ic, wacc, g_term, tax=0.21, years=10):
    """같은 엔진(dcf.value)으로 '현재 수익성 유지 + 성장 감속' 기업을 자본화한 EV ÷ 매출. 이익률이 0 이하이면 None"""
    if margin <= 0 or not s2c:
        return None
    d = {"rev0": rev, "growth": scenarios.growth_path({"start": growth, "end": g_term, "decay": 0.45 if growth > 0.5 else 0.7}, years),
         "margin": [margin] * years, "tax": tax, "s2c": s2c, "ic0": ic, "wacc": wacc, "g_term": g_term, "net_debt": 0.0, "shares": 1.0}
    return dcf.value(d)["ev"] / rev


def steady_state_table(wacc, g, tax=0.21, roics=(0.10, 0.15, 0.20, 0.30, 0.50), margins=(0.15, 0.22, 0.30, 0.40)):
    """McKinsey 핵심 가치 동인 공식 — 정상 상태 EV/NOPAT(다음 해)와 EV/매출"""
    rows = []
    for r in roics:
        ev_nopat = (1 - g / r) / (wacc - g)
        rows.append({"roic": r, "ev_nopat": ev_nopat, "ev_sales": {m: ev_nopat * m * (1 - tax) for m in margins}})
    return rows


def analyze(dp, base_drivers, mcap, wacc, g_term):
    """datapack + v2 기본 시나리오 → 멀티플 분석 dict"""
    tax = dp.get("tax", 0.21)
    fin = dp.get("financials") or {}
    net_debt = (dp["profile"].get("debt") or 0) - (dp["profile"].get("cash") or 0)
    ev = mcap + net_debt
    rev = fin.get("rev_ttm")
    cur = ev / rev if rev else None
    peers = []
    for p in dp.get("peers") or []:
        if not all(p.get(k) is not None for k in ("rev", "ebit_margin", "mcap", "pb", "ev_sales", "growth")):
            continue
        roic, roic_ex, s2c, ic = peer_fundamentals(p, tax)
        w = warranted_ev_sales(p["rev"], p["growth"], p["ebit_margin"], s2c, ic, wacc, g_term, tax) if roic is not None else None
        w = w if w and w > 0 else None   # 이익률·ROIC가 음수면 내재 멀티플을 정의할 수 없다 — 심리 배율에서 뺀다
        peers.append({**p, "roic": roic, "roic_ex": roic_ex, "s2c": s2c, "warranted": w, "ratio": (p["ev_sales"] / w) if w else None})
    tw = dcf.value(base_drivers)["ev"] / rev if rev else None   # 대상 내재 = v2 기본 시나리오 EV ÷ TTM 매출
    ratios = [x["ratio"] for x in peers if x["ratio"]]
    acts, warrs = [x["ev_sales"] for x in peers], [x["warranted"] for x in peers if x["warranted"]]
    med_act, med_w, med_r = pct(acts, 0.5), pct(warrs, 0.5), pct(ratios, 0.5)
    out = {"current": cur, "ev": ev, "rev": rev, "peers": peers, "target_warranted": tw,
           "peer_range": {"p25": pct(acts, 0.25), "p50": med_act, "p75": pct(acts, 0.75)},
           "sentiment": {"p25": pct(ratios, 0.25), "p50": med_r, "p75": pct(ratios, 0.75), "n": len(ratios)},
           "steady": steady_state_table(wacc, g_term, tax)}
    hist = [h["value"] for h in ((dp.get("history") or {}).get("ev_sales") or []) if h.get("value")]
    if hist:
        out["history"] = {"p10": pct(hist, 0.1), "p50": pct(hist, 0.5), "p90": pct(hist, 0.9), "n": len(hist),
                          "basis": (dp.get("history") or {}).get("basis", "")}
    if cur and med_act and tw and med_w and med_r and tw > 0:
        total = math.log(cur / med_act)
        firm = math.log((cur / tw) / med_r)            # 대상의 시장÷내재 배율이 동종 중앙보다 얼마나 높은가(기업 고유)
        out["decomp"] = {"total": total, "fundamental": total - firm, "firm": firm,   # 두 몫의 곱 = 전체(정확히 맞아떨어짐)
                         "fund_only": math.log(tw / med_w)}                         # 참고: 심리를 빼고 펀더멘털만 비교
        out["rational"] = {k: tw * out["sentiment"][k] for k in ("p25", "p50", "p75") if out["sentiment"][k]}
        out["rational_value_x"] = {k: (v * rev - net_debt) / mcap for k, v in out["rational"].items()}
    # 정상 상태(5년차) 멀티플을 지금으로 할인한 교차 확인 — 5년차 이익률·ROIC는 v2 기본 시나리오에서
    rows, _ = dcf.project(base_drivers)
    if len(rows) >= 6 and rows[5]["roic"] and rows[5]["roic"] > g_term:
        r5, m5, rev5 = rows[5]["roic"], rows[4]["margin"], rows[4]["rev"]
        evn = (1 - g_term / r5) / (wacc - g_term)
        ev5 = evn * rows[5]["nopat"]
        pv_mid = sum(x["fcff"] / (1 + wacc) ** x["t"] for x in rows[:5])
        out["forward"] = {"roic5": r5, "margin5": m5, "ev_nopat": evn, "ev_sales5": ev5 / rev5,
                          "value_x": (ev5 / (1 + wacc) ** 5 + pv_mid - net_debt) / mcap}
    if len([x for x in peers if x["warranted"]]) >= 3:
        pts = [(x["warranted"], x["ev_sales"]) for x in peers if x["warranted"]]
        n = len(pts)
        mx, my = sum(a for a, _ in pts) / n, sum(b for _, b in pts) / n
        sxx = sum((a - mx) ** 2 for a, _ in pts) or 1e-9
        b = sum((a - mx) * (c - my) for a, c in pts) / sxx
        a0 = my - b * mx
        ss_res = sum((c - (a0 + b * a)) ** 2 for a, c in pts)
        ss_tot = sum((c - my) ** 2 for _, c in pts) or 1e-9
        out["regression"] = {"a": a0, "b": b, "r2": 1 - ss_res / ss_tot, "n": n, "implied": (a0 + b * tw) if tw else None}
    return out


def report_blocks(m, unit, mcap, name="대상"):
    """리포트 절 블록 — 굵게만 쓰고 HTML은 쓰지 않는다(report_html 규칙)"""
    B = []
    f = lambda x, d=1: "-" if x is None else f"{x:.{d}f}"
    rows = [[x["ticker"], f(x["ev_sales"]), f"{x['growth']:.0%}", f"{x['ebit_margin']:.0%}",
             ("-" if x["roic"] is None else f"{x['roic']:.0%}") + " / " + ("-" if x.get("roic_ex") is None else f"{x['roic_ex']:.0%}"),
             f(x["s2c"], 2), f(x["warranted"]), f(x["ratio"], 2)] for x in m["peers"]]
    pr, s = m["peer_range"], m["sentiment"]
    rows.append(["**동종 중앙**", f(pr["p50"]), "", "", "", "", "", f(s["p50"], 2)])
    rows.append([f"**{name}**", f(m["current"]), "", "", "", "", f(m["target_warranted"]), f(m["current"] / m["target_warranted"], 2) if m.get("target_warranted") and m["target_warranted"] > 0 else "-"])
    B.append({"type": "table", "title": "동종 레인지와 펀더멘털 내재 멀티플 (EV/매출, 최근 12개월)",
              "headers": ["회사", "EV/매출", "성장", "영업이익률", "ROIC 영업권 포함/제외", "매출÷투하자본(영업권 제외)", "펀더멘털 내재", "시장÷내재"], "rows": rows})
    bars = [{"label": "현재", "bars": [{"name": "EV/매출", "color": "e", "value": round(m["current"], 1)}]}]
    if m.get("history"):
        h = m["history"]
        bars.append({"label": f"자기 과거 중앙(10~90분위 {h['p10']:.0f}~{h['p90']:.0f})", "bars": [{"name": "EV/매출", "color": "a", "value": round(h["p50"], 1)}]})
    bars.append({"label": f"동종 중앙(25~75분위 {pr['p25']:.0f}~{pr['p75']:.0f})", "bars": [{"name": "EV/매출", "color": "b", "value": round(pr["p50"], 1)}]})
    if m.get("target_warranted"):
        bars.append({"label": "펀더멘털 내재(v2 기본)", "bars": [{"name": "EV/매출", "color": "c", "value": round(m["target_warranted"], 1)}]})
    if m.get("rational"):
        r = m["rational"]
        bars.append({"label": f"합리적(내재 × 섹터 심리, {r.get('p25', 0):.0f}~{r.get('p75', 0):.0f})", "bars": [{"name": "EV/매출", "color": "d", "value": round(r["p50"], 1)}]})
    B.append({"type": "chart", "chart": {"kind": "hbars", "title": "EV/매출 — 과거·동종·펀더멘털·합리적 멀티플 (배)", "unit": "배", "rows": bars,
              "note": "펀더멘털 내재 = 같은 WACC·계속가치 규칙으로 각 회사의 성장·이익률·자본 회전율을 자본화한 EV ÷ 매출. 섹터 심리 = 동종의 시장 ÷ 내재 배율"}})
    if m.get("decomp"):
        d = m["decomp"]
        pc = lambda x: f"{math.exp(x) - 1:+.0%}"
        B.append({"type": "p", "text": f"**할인·프리미엄 분해:** {name}의 EV/매출은 동종 중앙 대비 **{pc(d['total'])}** = 동종과 같은 섹터 심리를 받는다면 펀더멘털(성장·이익률·ROIC)로 정당한 몫 {pc(d['fundamental'])} × "
                  f"{name}에만 얹힌 기업 고유 몫 **{pc(d['firm'])}**(두 몫을 곱하면 전체). 심리를 빼고 펀더멘털만 비교하면 동종 중앙 내재 대비 {pc(d['fund_only'])}. "
                  "기업 고유 몫이 양(+)이면 시장이 동종보다 더 큰 기대를 얹은 것(할인이 덜 됐다), 음(−)이면 더 할인한 것이다."})
    if m.get("rational_value_x"):
        rv = m["rational_value_x"]
        B.append({"type": "p", "text": f"**합리적 멀티플:** {m['rational']['p50']:.1f}배(섹터 심리 25~75분위 {m['rational'].get('p25', 0):.1f}~{m['rational'].get('p75', 0):.1f}배) → 주주가치 ÷ 시가총액 "
                  f"**{rv['p50']:.2f}배**({rv.get('p25', 0):.2f}~{rv.get('p75', 0):.2f}배). 현재 {m['current']:.1f}배와의 차이가 시장이 동종보다 더 얹은 기대다."})
    heavy = [x["ticker"] for x in m["peers"] if (x.get("goodwill") or 0) + (x.get("intangibles") or 0) > 0.3 * (x["mcap"] / x["pb"] if x.get("pb") else 1e9)]
    if heavy:
        B.append({"type": "p", "text": f"한계: 동종 영업이익률은 GAAP(인수 무형자산 상각 포함)이라 인수가 큰 {', '.join(heavy)}는 내재 멀티플이 낮게·심리 배율이 높게 나온다 → 합리적 멀티플이 위로 치우칠 수 있다(상각 전 이익 EBITA로 바꾸면 낮아질 가능성). 동종 성장은 최근 분기 전년 대비, 표본 {len(m['peers'])}곳 — 방향 판단용."})
    if m.get("regression") and m["regression"]["b"] > 0:
        g = m["regression"]
        B.append({"type": "p", "text": f"동종 {g['n']}사 회귀(시장 EV/매출 = {g['a']:.1f} + {g['b']:.2f} × 펀더멘털 내재, R² {g['r2']:.2f}) — 펀더멘털로 정당화되는 멀티플. "
                  + (f"{name}에 대입하면 {g['implied']:.1f}배." if g.get("implied") is not None else "") + (" 표본이 작아 참고용." if g["n"] < 6 else "")})
    st = m["steady"]
    ms = list(st[0]["ev_sales"])
    B.append({"type": "table", "title": "ROIC에 비례하는 정상 상태 멀티플 (맥킨지 가치 동인: EV/NOPAT = (1 − g/ROIC) ÷ (WACC − g))",
              "headers": ["ROIC", "EV/NOPAT"] + [f"EV/매출 @영업이익률 {x:.0%}" for x in ms],
              "rows": [[f"{r['roic']:.0%}", f"{r['ev_nopat']:.1f}"] + [f"{r['ev_sales'][x]:.1f}" for x in ms] for r in st]})
    if m.get("forward"):
        fw = m["forward"]
        B.append({"type": "p", "text": f"정상 상태 교차 확인: v2 기본 시나리오의 5년차 ROIC {fw['roic5']:.0%}·영업이익률 {fw['margin5']:.0%}이면 정상 상태 EV/NOPAT {fw['ev_nopat']:.1f}배(5년차 EV/매출 {fw['ev_sales5']:.1f}배). "
                  f"이를 지금으로 할인하면 주주가치 ÷ 시가총액 {fw['value_x']:.2f}배 — 고성장 기업은 현재 멀티플이 아니라 정상 상태 멀티플을 할인해 비교한다(맥킨지 『Valuation』 멀티플 장)."})
    return B
