"""텐배거 리포트 'M&A 시너지' 절 (마스터 지시 2026-11-03 "상장회사의 M&A 이후 효과를 다룰 때 비즈니스 시너지가 어떻게 나는지
시각물과 모델링으로 자세히 설명")

숫자는 여기서 계산한다. 모델은 datapack "ma"에 거래 조건과 시너지 근거만 쓴다. 금액 단위는 datapack unit(보통 B$).
datapack "ma":
  {"deals": [{"target": "Maverick Power", "closed": "2026-10-01", "price": 1.75, "target_rev": 0.6, "target_ebitda": 0.15, "target_ni": 0.08,
              "premium": 0.35,                                   # 인수 전 가치 대비 웃돈 몫(모르면 생략)
              "financing": {"cash": 0.5, "debt": 1.25, "rate": 0.055, "new_shares": 0},
              "integration_cost": 0.06,                          # 일회성 통합 비용 합계
              "synergies": [{"type": "원가|매출|설비투자|세금", "name": "조달 통합", "run_rate": 0.04, "full_year": 2028, "prob": 0.8,
                             "mechanism": "어떻게 생기나 한 줄", "margin": 0.3,  # 매출 시너지만 — 그 매출의 이익률
                             "source": "회사 발표"}]}],
   "acquirer": {"eps": 4.1, "shares": 0.162, "tax": 0.21, "year0": 2026}}   # 인수 기업 다음 해 EPS·주식 수(B주)
  M&A가 없으면 {"none": "이유"}.
모델: 시너지는 마감 연도부터 full_year까지 직선 램프. 이익 기여 = 원가·설비투자·세금은 run_rate, 매출은 run_rate × margin, 확률 가중.
가치 = 세후 시너지 이익 기여의 5년 현금흐름 + 말기 가치(할인율 r, 성장 0) − 통합 비용. 웃돈과 비교해 '값을 치를 만한가'를 본다.
EPS 효과 = (대상 순이익 + 세후 시너지 − 세후 이자) ÷ (주식 수 + 신주) − 기존 EPS.
"""
YEARS = 4
UNKNOWN = "미확인"


def contribution(s, year, closed_year):
    if year < closed_year:
        return 0.0
    span = max(s["full_year"] - closed_year, 1)
    ramp = min(1.0, (year - closed_year + 1) / (span + 1))
    base = s["run_rate"] * (s.get("margin", 1.0) if s["type"] == "매출" else 1.0)
    return base * ramp * s.get("prob", 1.0)


def deal_model(d, acq, r):
    cy = int(str(d["closed"])[:4])
    y0 = acq.get("year0", cy)
    years = list(range(y0, y0 + YEARS))
    tax = acq.get("tax", 0.21)
    by_type = {}
    for s in d["synergies"]:
        by_type.setdefault(s["type"], [0.0] * len(years))
        for i, y in enumerate(years):
            by_type[s["type"]][i] += contribution(s, y, cy)
    total = [sum(v[i] for v in by_type.values()) for i in range(len(years))]
    full = sum(s["run_rate"] * (s.get("margin", 1.0) if s["type"] == "매출" else 1.0) * s.get("prob", 1.0) for s in d["synergies"])
    cfs = [(contribution_total(d, y, cy)) * (1 - tax) for y in range(cy, cy + 5)]
    pv = sum(cf / (1 + r) ** (i + 1) for i, cf in enumerate(cfs)) + full * (1 - tax) / r / (1 + r) ** 5
    value = pv - d.get("integration_cost", 0.0)
    fin = d.get("financing") or {}
    interest = fin.get("debt", 0.0) * fin.get("rate", 0.0) * (1 - tax)
    eps0, sh = acq.get("eps"), acq.get("shares")
    eps = []
    if eps0 and sh:
        for i in range(len(years)):
            ni = eps0 * sh + d.get("target_ni", 0.0) + total[i] * (1 - tax) - interest
            eps.append(ni / (sh + fin.get("new_shares", 0.0)) / eps0 - 1)
    paid = d["price"] * d["premium"] / (1 + d["premium"]) if d.get("premium") is not None else None
    return {"years": years, "by_type": by_type, "total": total, "full": full, "value": value, "paid_premium": paid, "eps": eps,
            "multiple": d["price"] / d["target_ebitda"] if d.get("target_ebitda") else None,
            "multiple_syn": d["price"] / (d["target_ebitda"] + full) if d.get("target_ebitda") else None}


def contribution_total(d, y, cy):
    return sum(contribution(s, y, cy) for s in d["synergies"])


def _m(v, unit):
    return UNKNOWN if v is None else f"{v:,.2f}{unit}"


def _p(v):
    return UNKNOWN if v is None else f"{v * 100:+.1f}%"


def section(dp, r=0.09):
    ma = (dp or {}).get("ma")
    if not ma:
        raise SystemExit("datapack에 ma가 없다(scripts/tenbagger/ma_view.py 맨 위) — M&A가 없으면 {'none': '이유'}, 옛 리포트 정정은 --legacy")
    if ma.get("none"):
        return None
    unit = " " + str(dp.get("unit", "B$"))
    acq = ma.get("acquirer") or {}
    B, cols = [], {"원가": "c", "매출": "d", "설비투자": "e", "세금": "a"}
    for d in ma["deals"]:
        m = deal_model(d, acq, r)
        head = f"**{d['target']} 인수({d['closed']}, {_m(d['price'], unit)}): 시너지가 다 나면 연 {_m(m['full'], unit)}(확률 가중 이익 기여)"
        if m["multiple"]:
            head += f", 인수 배수 EV/EBITDA {m['multiple']:.1f}배 → 시너지 반영 {m['multiple_syn']:.1f}배"
        head += ".**"
        head += f" 세후 시너지 가치는 통합 비용을 빼고 {_m(m['value'], unit)}"
        if m["paid_premium"] is not None:
            head += f"로, 낸 웃돈 {_m(m['paid_premium'], unit)}의 {m['value'] / m['paid_premium']:.1f}배다" if m["paid_premium"] else ""
        head += "."
        if m["eps"]:
            head += f" EPS 효과는 {m['years'][0]}년 {_p(m['eps'][0])}에서 {m['years'][-1]}년 {_p(m['eps'][-1])}."
        B.append({"type": "hl", "text": head})
        B.append({"type": "chart", "chart": {"kind": "bars", "stack": True, "title": f"{d['target']} 시너지 램프(종류별, 확률 가중)", "unit": unit.strip(),
                                             "categories": [str(y) for y in m["years"]],
                                             "series": [{"name": k, "color": cols.get(k, "b"), "values": [round(v, 3) for v in vals]} for k, vals in m["by_type"].items()]}})
        bars = [["시너지 가치(세후, 통합 비용 차감)", m["value"]]]
        if m["paid_premium"] is not None:
            bars.append(["낸 웃돈", m["paid_premium"]])
        B.append({"type": "chart", "chart": {"kind": "hbars", "w": 480, "label_w": 180, "title": "시너지 가치 vs 웃돈", "unit": unit.strip(),
                                             "rows": [{"label": a, "bars": [{"name": a, "color": "d" if i == 0 else "b", "value": round(v, 3)}]} for i, (a, v) in enumerate(bars)]}})
        if m["eps"]:
            B.append({"type": "chart", "chart": {"kind": "line", "title": "EPS 효과(인수 기업, 기존 대비)", "unit": "%", "series": [{"name": "EPS 효과", "color": "c", "points": [[str(y), round(e * 100, 1)] for y, e in zip(m["years"], m["eps"])]}]}})
        B.append({"type": "table", "title": f"{d['target']} 시너지가 생기는 길", "headers": ["종류", "시너지", "연 규모", "완성", "확률", "어떻게 생기나", "근거"],
                  "rows": [[s["type"], s["name"], _m(s["run_rate"], unit) + (f"(이익률 {s['margin'] * 100:.0f}%)" if s["type"] == "매출" and s.get("margin") is not None else ""),
                            str(s["full_year"]), f"{s.get('prob', 1) * 100:.0f}%", s.get("mechanism", ""), s.get("source", "")] for s in d["synergies"]]})
    B.append({"type": "p", "text": f"시너지 가치 = 세후 이익 기여 5년 + 말기 가치(할인율 {r * 100:.0f}%, 성장 0) − 통합 비용. 매출 시너지는 그 매출의 이익률만 반영하고, 모든 시너지에 실현 확률을 곱했다."})
    return {"h2": "M&A 시너지", "blocks": B}
