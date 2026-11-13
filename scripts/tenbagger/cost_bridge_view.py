"""'마진 구조' 절의 매출 → 매출총이익 → 영업이익 비용 다리 (마스터 지시 2026-11-03 "매출 → Gross Profit으로 갈 때 비용 요인이 영향을
주고 그 비용 요인의 강도가 어떠한지 시각화와 수치화하라. BOM과 OPEX를 뜯어보는 것처럼 분석하라")

재료: datapack "quarters_hist"(공시 분기 손익, scripts/tenbagger/quarters.py)와 "margin"(비용 요인·BOM, margin_view.py).
계산은 모두 여기서 한다.
- 다리: 최근 4분기 합(TTM) 매출 100 기준. 매출원가는 margin.costs의 매출원가 요인으로 나누고, 공시 매출원가와의 차이는 '기타 매출원가'.
  OPEX는 공시 항목(연구개발·판관비·감가상각·기타)으로 나눈다.
- 강도(비용 요인마다): ① 비중(매출 대비) ② 추세(1년 전 TTM 대비 %p, 마진 기여는 부호 반대) ③ 충격(단가 +shock 시 GPM·OPM 변화, 전가 반영)
  ④ 탄력(분기 수준 회귀 비용 = a + b × 매출 — b = 매출 1당 변동비, 고정비 몫 = a ÷ 평균 비용). 공시 항목은 ②④를, BOM 요인은 ①②③을 잰다.
"""
import margin_view

UNKNOWN = "미확인"
LINES = (("cogs", "매출원가"), ("rd", "연구개발"), ("sga", "판관비"), ("da", "감가상각"), ("other", "기타 영업비용"))


def ttm(q, end):
    """end 번째 분기까지 4분기 합 {항목: 값}. 네 분기가 다 있어야 한다"""
    part = q[end - 3:end + 1]
    if len(part) < 4:
        return None
    out = {}
    for k in ("rev", "gp", "op") + tuple(k for k, _ in LINES):
        vals = [r.get(k) for r in part]
        out[k] = sum(vals) if all(v is not None for v in vals) else None
    if out["rev"] and out["cogs"] is None and out["gp"] is not None:
        out["cogs"] = out["rev"] - out["gp"]
    return out


def elastic(q, key):
    """분기 비용 = a + b × 매출 — (b, 고정비 몫). 8분기 이상"""
    pts = [(r["rev"], r[key]) for r in q if r.get("rev") and r.get(key) is not None]
    if len(pts) < 8:
        return None
    n = len(pts)
    mx, my = sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    if not sxx or not my:
        return None
    b = sum((x - mx) * (y - my) for x, y in pts) / sxx
    a = my - b * mx
    return b, max(min(a / my, 1.0), -1.0)


def compute(dp):
    q = [r for r in (dp.get("quarters_hist") or {}).get("q") or [] if r.get("rev")]
    now, prior = ttm(q, len(q) - 1), ttm(q, len(q) - 5)
    if not now or not now["rev"] or now["cogs"] is None:
        return None
    rev = now["rev"]
    shock = margin_view.config()["margin"]["shock"]
    cogs_factors = [c for c in (dp.get("margin") or {}).get("costs") or [] if c.get("stage") == "매출원가"]
    steps, rows = [("매출", 100.0, "total")], []
    named = 0.0
    for c in sorted(cogs_factors, key=lambda c: -c["pct_rev"]):
        v = c["pct_rev"] * 100
        named += v
        prior_pct = margin_view._num(c.get("prior_pct"))
        rows.append({"name": c["name"], "kind": "매출원가 요인", "pct": c["pct_rev"], "trend": None if prior_pct is None else c["pct_rev"] - prior_pct,
                     "shock": -c["pct_rev"] * shock, "elastic": None, "fixed": margin_view._num(c.get("fixed")), "driver": c.get("driver")})
        steps.append((c["name"], -v, "cost"))
    rest = now["cogs"] / rev * 100 - named
    if abs(rest) >= 0.5:
        steps.append(("기타 매출원가", -rest, "cost"))
    steps.append(("매출총이익", (rev - now["cogs"]) / rev * 100, "total"))
    for k, name in LINES[1:]:
        if now.get(k):
            steps.append((name, -now[k] / rev * 100, "cost"))
    if now.get("op") is not None:
        steps.append(("영업이익", now["op"] / rev * 100, "total"))
    for k, name in LINES:
        if not now.get(k):
            continue
        pct = now[k] / rev
        tr = None if not prior or not prior.get(k) or not prior["rev"] else pct - prior[k] / prior["rev"]
        e = elastic(q, k)
        rows.append({"name": name, "kind": "공시 항목", "pct": pct, "trend": tr, "shock": -pct * shock if k == "cogs" else None,
                     "elastic": None if not e else e[0], "fixed": None if not e else e[1], "driver": None})
    hist = []
    for r in q:
        if r.get("cogs") is None and r.get("gp") is not None:
            r = {**r, "cogs": r["rev"] - r["gp"]}
        hist.append(r)
    return {"steps": steps, "rows": rows, "shock": shock, "hist": hist, "now": now, "prior": prior}


def _pp(x, d=1):
    return UNKNOWN if x is None else f"{x * 100:+.{d}f}%p"


def blocks(dp):
    c = compute(dp)
    if not c:
        return []
    now = c["now"]
    gpm = (now["rev"] - now["cogs"]) / now["rev"]
    strongest = max((r for r in c["rows"] if r["kind"] == "매출원가 요인"), key=lambda r: r["pct"], default=None)
    head = f"**매출 100 중 매출원가 {now['cogs'] / now['rev'] * 100:.1f}, 매출총이익 {gpm * 100:.1f}(최근 4분기, 공시).**"
    if strongest:
        head += f" 매출원가 요인 중 {strongest['name']}이 매출의 {strongest['pct'] * 100:.1f}%로 가장 무겁고, 단가가 +{c['shock'] * 100:.0f}% 오르면 GPM이 {_pp(strongest['shock'], 2)} 움직인다."
    cg = next((r for r in c["rows"] if r["name"] == "매출원가" and r["elastic"] is not None), None)
    if cg:
        head += f" 분기 회귀로 매출 1이 늘 때 매출원가는 {cg['elastic']:.2f} 늘고, 매출원가의 고정비 몫은 {cg['fixed'] * 100:.0f}%다."
    B = [{"type": "hl", "text": head},
         {"type": "chart", "chart": {"kind": "waterfall", "title": "매출 → 매출총이익 → 영업이익(매출 = 100, 최근 4분기)", "unit": "",
                                     "steps": [{"label": n, "value": round(v, 1), "kind": k} for n, v, k in c["steps"]]}}]
    # 분기 비용 비중 추이를 매출→영업이익 다리 바로 다음에(마스터 지시 2026-11-13). '1년 전 대비 마진 기여' 그림은 뺀다 — 같은 값이 표의 '마진 기여' 열에 있다
    h = c["hist"]
    series = []
    for k, name, col in (("cogs", "매출원가", "c"), ("sga", "판관비", "b"), ("rd", "연구개발", "d"), ("op", "영업이익률", "a")):
        pts = [[r["period"][:7], round(r[k] / r["rev"] * 100, 1)] for r in h if r.get(k) is not None]
        if len(pts) >= 4:
            series.append({"name": name, "color": col, "points": pts})
    if series:
        B.append({"type": "chart", "chart": {"kind": "line", "title": "분기 비용 비중 추이(매출 대비, 공시)", "unit": "%", "series": series}})
    rows = []
    for r in sorted(c["rows"], key=lambda r: (r["kind"] != "매출원가 요인", -r["pct"])):
        rows.append([r["name"], r["kind"], f"{r['pct'] * 100:.1f}%", _pp(r["trend"]), _pp(None if r["trend"] is None else -r["trend"]),
                     _pp(r["shock"], 2), UNKNOWN if r["elastic"] is None else f"{r['elastic']:.2f}", UNKNOWN if r["fixed"] is None else f"{r['fixed'] * 100:.0f}%"])
    B.append({"type": "table", "title": f"비용 요인 강도 — 비중·추세·충격(+{c['shock'] * 100:.0f}%)·탄력",
              "headers": ["비용", "구분", "매출 대비", "1년 변화", "마진 기여", "충격 시 마진", "매출 탄력", "고정비 몫"], "rows": rows})
    B.append({"type": "p", "text": "매출 탄력 = 분기 비용을 매출에 회귀한 기울기(매출 1당 변동비), 고정비 몫 = 절편 ÷ 평균 비용. 표본이 8분기 미만이면 미확인. 매출원가 요인 비중은 margin 재료의 추정이 섞여 있고, 공시 매출원가와의 차이는 '기타 매출원가'로 둔다."})
    return B
