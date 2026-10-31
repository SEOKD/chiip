"""목표주가 (마스터 지시 2026-11-01 "현 시점 목표 주가를 월스트리트 IB 리서치 하우스 모델링으로 산정하고 이를 기준으로 업사이드를 측정. 기본 시나리오가 목표 주가라고 생각하면
그것으로, 기본과 강세 사이에 도달할 확률이 높아 보이면 그 사이로. DCF 한 요인에만 의존하지 말고 차트 기법 상승 여력, 내러티브 멀티플 프리미엄 확정 여력까지 반영")

약세~기본~강세 축에서 요인별로 가리키는 주가를 재고, 가중 평균한 기울기(tilt, −1~+1)만큼 기본에서 옮긴다. 0이면 기본, +1이면 강세, −1이면 약세다.
요인: 시나리오 확률 가중 · DCF 12개월 뒤 값 · 차트(200일선·52주 고점·피보나치 되돌림과 확장) · 내러티브 프리미엄 여력. 재료가 없는 요인은 빼고 나머지 비중을 다시 맞춘다.
상수는 config/tenbagger.yaml target_price(등록부 prm-tb-pt-*). 판단 조정은 모델이 이유와 함께 datapack target_view {"adj": 0.1, "why": "..."}에 쓴다.
"""
import levels

CASE = {"약세": "bear", "강세": "bull"}


def chart_target(daily, cfg):
    """주류 기법의 저항선으로 12개월 상승 여력을 잰다. 상승 추세면 둘째 저항선, 하락 추세면 첫째, 그 사이면 둘의 평균. 재료가 모자라면 None"""
    if len(daily) < 200:
        return None
    price = daily[-1]["c"]
    ma50, ma200 = levels.sma(daily, 50), levels.sma(daily, 200)
    sw = levels.dominant(levels.resample(daily, "W"), "주봉")
    ret, _ = levels.fib(sw["low"], sw["high"], sw["up"])
    res = [(ma200, "200일선"), (sw["high"], "52주 고점")] + [(v, f"피보나치 되돌림 {k}") for k, v in ret.items()]
    if price >= sw["high"] * cfg["near_high"]:   # 신고가 부근에는 위쪽 저항이 없어 확장 비율을 쓴다
        res += [(sw["low"] + e * (sw["high"] - sw["low"]), f"피보나치 확장 {e * 100:.1f}%") for e in levels.FIB_EXT]
    above = sorted((x for x in res if x[0] > price * (1 + cfg["min_gap"])), key=lambda x: x[0])
    if not above:
        return None
    up, down = price > ma200 and ma50 > ma200, price < ma200 and ma50 < ma200
    two = above[:2]
    if up and len(two) == 2:
        value, why = two[1][0], f"상승 추세, 둘째 저항선 {two[1][1]}"
    elif down or len(two) == 1:
        value, why = two[0][0], f"{'하락 추세, ' if down else ''}첫째 저항선 {two[0][1]}"
    else:
        value, why = (two[0][0] + two[1][0]) / 2, f"추세 혼조, {two[0][1]}·{two[1][1]} 평균"
    return {"price": value, "why": why}


def narrative_price(s, stage, room, net_debt, shares):
    """기본 이익에 내러티브 단계만큼 옮긴 멀티플을 곱한다 — 확산이면 강세 멀티플 쪽, 과밀·소멸이면 약세 멀티플 쪽"""
    cases = {k["name"]: k for k in s["cases"]}
    share = room.get(stage, 0.0)
    m0 = cases["기본"]["multiple"]
    m = m0 + abs(share) * (cases["강세" if share >= 0 else "약세"]["multiple"] - m0)
    k = cases["기본"]
    return k["eps"] * m if k.get("eps") is not None else (m * k["ebitda"] - net_debt) / shares


def signal(p, s):
    """요인 주가의 축 위 위치 −1~+1"""
    if p >= s["base"]:
        return min(1.0, (p - s["base"]) / (s["bull"] - s["base"])) if s["bull"] > s["base"] else 0.0
    return max(-1.0, (p - s["base"]) / (s["base"] - s["bear"])) if s["base"] > s["bear"] else 0.0


def reach(t, s):
    """목표주가 이상일 확률 — 세 시나리오를 구간으로 펴서 잇는다"""
    p = {k["name"]: float(k["prob"]) for k in s["cases"]}
    at_bear, at_base, at_bull = 1 - p["약세"] / 2, p["강세"] + p["기본"] / 2, p["강세"] / 2
    if t >= s["base"]:
        w = (t - s["base"]) / (s["bull"] - s["base"]) if s["bull"] > s["base"] else 0
        return at_base + w * (at_bull - at_base)
    w = (s["base"] - t) / (s["base"] - s["bear"]) if s["base"] > s["bear"] else 0
    return at_base + w * (at_bear - at_base)


def place(tilt):
    if abs(tilt) < 0.05:
        return "기본 시나리오"
    return f"기본과 강세 사이(강세 쪽 {tilt:.0%})" if tilt > 0 else f"약세와 기본 사이(약세 쪽 {-tilt:.0%})"


def build(s, dcf_ratio, ke, stage, view, daily, net_debt, shares, cfg, street=None):
    """{'target','upside','tilt','place','reach','factors','judge','why'} — s는 report_layout.scenario_build 결과, dcf_ratio는 기본 DCF 값 ÷ 시가총액"""
    w = cfg["weights"]
    chart = chart_target(daily, cfg["chart"])
    rows = [{"key": "scenario", "name": "시나리오 확률 가중", "price": s["weighted"], "why": "약세·기본·강세 확률로 가중"},
            {"key": "dcf", "name": "DCF 12개월 뒤 값", "price": s["price"] * dcf_ratio * (1 + ke), "why": f"기본 DCF를 자기자본비용 {ke:.1%}로 1년 굴림"},
            {"key": "narrative", "name": "내러티브 프리미엄 여력", "price": narrative_price(s, stage, cfg["narrative_room"], net_debt, shares), "why": f"단계 {stage or '미확인'}, 기본 이익에 옮긴 멀티플 적용"}]
    if chart:
        rows.insert(2, {"key": "chart", "name": "차트 상승 여력", **chart})
    total = sum(w[x["key"]] for x in rows)
    for x in rows:
        x.update({"weight": w[x["key"]] / total, "signal": signal(x["price"], s)})
    judge = max(-cfg["judge_cap"], min(cfg["judge_cap"], float((view or {}).get("adj") or 0)))
    tilt = max(-1.0, min(1.0, sum(x["weight"] * x["signal"] for x in rows) + judge))
    raw = s["base"] + tilt * ((s["bull"] - s["base"]) if tilt >= 0 else (s["base"] - s["bear"]))
    target = float(round(raw)) if raw >= cfg["round_above"] else round(raw, 1)
    return {"target": target, "upside": target / s["price"] - 1, "tilt": tilt, "place": place(tilt), "reach": reach(target, s), "factors": rows, "judge": judge,
            "why": (view or {}).get("why"), "street": street}


def table(pt, s):
    """밸류에이션 절의 산정 표"""
    cur = s["sym"]
    rows = [[x["name"], f"{x['weight']:.0%}", f"{cur}{x['price']:,.0f}", f"{x['signal']:+.2f}", x["why"]] for x in pt["factors"]]
    if pt["judge"]:
        rows.append(["판단 조정", "-", "-", f"{pt['judge']:+.2f}", str(pt.get("why") or "")])
    if pt.get("street"):
        rows.append(["애널리스트 평균(참고)", "-", f"{cur}{pt['street']:,.0f}", "-", "가중하지 않는 대조값"])
    rows.append(["**목표주가**", "", f"**{cur}{pt['target']:,.0f}**", f"**{pt['tilt']:+.2f}**", pt["place"]])
    return {"type": "table", "title": "목표주가 산정", "headers": ["요인", "비중", "가리키는 주가", "위치(−1 약세 · 0 기본 · +1 강세)", "근거"], "rows": rows}
