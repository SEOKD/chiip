"""텐배거 리포트 '매수 위치(일봉)' 절 (마스터 지시 2026-11-03 "주가별 업사이드는 일봉 기준으로만. 차트 기법에 따라 지지선을 면밀히
분석하고 해당 위치에서 업사이드가 얼마나 있는지 — 좋은 종목이라도 나쁜 위치에 사면 알파가 떨어진다")

일봉만 쓴다. 지지선 = 일봉 50·200일선 + 일봉 지배 스윙(ATR 지그재그 마지막 완료 다리)의 피보나치 되돌림 + 스윙 저점 + 최근 120일 지그재그 저점.
가까운 선은 levels.cluster로 묶고, 서로 다른 기법이 겹칠수록 강하다(강도). 저항선도 같은 방식(현재가 위).
가격대마다(현재가·지지 구간): 목표주가까지 업사이드, 첫 일봉 저항까지 업사이드, 다음 지지까지 하방, 손익비 = 업사이드 ÷ 하방.
위치 판정: 현재가가 가장 가까운 지지 구간에서 ATR(14일) 몇 배 위에 있나 — 1배 이내 '지지 근접', 3배 넘으면 '지지에서 멀다'.
매수·매도 지시가 아니라 가격대별 기대값 참고표다.
"""
import levels

ATR_NEAR, ATR_FAR = 1.0, 3.0


def daily_levels(daily):
    price = daily[-1]["c"]
    sw = levels.dominant(daily, "일봉")
    ret, _ = levels.fib(sw["low"], sw["high"], sw["up"])
    lv = []
    for n in (20, 50, 200):
        v = levels.sma(daily, n)
        if v:
            lv.append({"price": v, "src": f"{n}일선", "kind": f"ma{n}", "w": 1.0 if n != 20 else 0.5})
    lv += [{"price": v, "src": f"피보 {k}", "kind": "fib", "w": 1.0} for k, v in ret.items()]
    lv.append({"price": sw["low"], "src": "스윙 저점", "kind": "swing", "w": 1.0})
    lv.append({"price": sw["high"], "src": "스윙 고점", "kind": "swing", "w": 1.0})
    tail = daily[-120:]
    for p in levels.zigzag(tail, levels.zz_threshold(tail, "일봉")):
        lv.append({"price": p[1], "src": "120일 지그재그 " + ("저점" if p[2] == "L" else "고점"), "kind": "zz", "w": 0.8})
    if price >= sw["high"] * 0.97:
        lv += [{"price": sw["low"] + e * (sw["high"] - sw["low"]), "src": f"피보 확장 {e * 100:.1f}%", "kind": "ext", "w": 0.8} for e in levels.FIB_EXT]
    groups = levels.cluster(lv)
    sup = sorted([g for g in groups if g["hi"] < price * 0.998], key=lambda g: -g["mid"])
    res = sorted([g for g in groups if g["lo"] > price * 1.002], key=lambda g: g["mid"])
    atr = levels.atr_pct(daily) * price
    return {"price": price, "swing": sw, "support": sup[:4], "resistance": res[:3], "atr": atr}


def ladder(lv, target):
    """가격대별 업사이드·하방·손익비 — 현재가와 지지 구간마다"""
    rows = []
    points = [("현재가", lv["price"], None)] + [(f"지지 {i + 1}", g["mid"], g) for i, g in enumerate(lv["support"])]
    for i, (name, p, g) in enumerate(points):
        below = next((s["mid"] for s in lv["support"] if s["mid"] < p * 0.995), None)
        above = [x["mid"] for x in lv["support"] + lv["resistance"] if x["mid"] > p * 1.005]
        first_res = min(above) if above else None
        up_t = target / p - 1 if target else None
        down = (below / p - 1) if below else None
        rows.append({"name": name, "price": p, "group": g, "up_target": up_t, "up_res": (first_res / p - 1) if first_res else None, "down": down,
                     "rr": (up_t / -down) if up_t is not None and down else None})
    return rows


def place(lv):
    if not lv["support"] or not lv["atr"]:
        return "지지선 미확인", None
    k = (lv["price"] - lv["support"][0]["mid"]) / lv["atr"]
    return ("지지 근접" if k <= ATR_NEAR else ("지지에서 멀다" if k > ATR_FAR else "중간")), k


def _m(v):
    return "미확인" if v is None else (f"${v:,.2f}" if v < 100 else f"${v:,.0f}")


def _p(v):
    return "미확인" if v is None else f"{v * 100:+.1f}%"


def section(daily, target):
    if len(daily) < 200:
        return None
    lv = daily_levels(daily)
    rows = ladder(lv, target)
    where, k = place(lv)
    now = rows[0]
    best = max((r for r in rows if r["rr"] is not None), key=lambda r: r["rr"], default=None)
    head = f"**현재가 {_m(lv['price'])}는 '{where}'" + (f"(가장 가까운 일봉 지지 {_m(lv['support'][0]['mid'])}에서 ATR {k:.1f}배 위)" if k is not None else "") + ".**"
    head += f" 이 자리에서 목표주가까지 {_p(now['up_target'])}, 첫 일봉 저항까지 {_p(now['up_res'])}, 다음 지지까지 하방 {_p(now['down'])}"
    head += f", 손익비 {now['rr']:.1f}배." if now["rr"] is not None else "."
    if best and best["name"] != "현재가":
        head += f" 손익비는 {best['name']} {_m(best['price'])}에서 {best['rr']:.1f}배로 가장 높다(목표주가까지 {_p(best['up_target'])})."
    B = [{"type": "hl", "text": head}]
    B.append({"type": "table", "title": "가격대별 업사이드(일봉 기준)", "headers": ["가격대", "가격", "목표주가까지", "첫 저항까지", "다음 지지까지", "손익비", "근거 기법(강도)"],
              "rows": [[r["name"], _m(r["price"]), _p(r["up_target"]), _p(r["up_res"]), _p(r["down"]), "미확인" if r["rr"] is None else f"{r['rr']:.1f}",
                        "-" if not r["group"] else f"{' · '.join(sorted({x['src'] for x in r['group']['items']}))}({r['group']['strength']:.1f})"] for r in rows]})
    if lv["resistance"]:
        B.append({"type": "table", "title": "일봉 저항", "headers": ["저항", "가격", "현재가 대비", "근거 기법(강도)"],
                  "rows": [[f"저항 {i + 1}", _m(g["mid"]), _p(g["mid"] / lv["price"] - 1), f"{' · '.join(sorted({x['src'] for x in g['items']}))}({g['strength']:.1f})"] for i, g in enumerate(lv["resistance"])]})
    b = daily[-120:]
    lo_v, hi_v = min(x["l"] for x in b), max(x["h"] for x in b)
    hl = [{"y": g["mid"], "label": f"지지 {i + 1} {_m(g['mid'])}", "color": "d"} for i, g in enumerate(lv["support"]) if g["mid"] >= lo_v * 0.85]
    hl += [{"y": g["mid"], "label": f"저항 {i + 1} {_m(g['mid'])}", "color": "b"} for i, g in enumerate(lv["resistance"]) if g["mid"] <= hi_v * 1.25]
    if target and target <= hi_v * 1.6:
        hl.append({"y": target, "label": f"목표주가 {_m(target)}", "color": "c"})
    B.append({"type": "chart", "chart": {"kind": "candle", "title": "일봉 지지·저항과 목표주가", "unit": "$", "bars": [[x["date"], x["o"], x["h"], x["l"], x["c"]] for x in b], "hlines": hl,
                                         "note": f"일봉 지배 스윙: {lv['swing']['basis']}. 강도 = 같은 가격대에 겹친 서로 다른 기법의 가중 합."}})
    B.append({"type": "p", "text": "일봉만 쓴다(주봉·월봉 제외). 손익비 = 목표주가까지 업사이드 ÷ 다음 지지까지 하방. 가격대별 기대값 참고표이며 매수·매도 시점 지시가 아니다."})
    return {"h2": "매수 위치(일봉)", "blocks": B, "place": where}
