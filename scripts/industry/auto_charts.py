"""Industry Report 시각물 — 데이터팩의 구조화된 숫자로 그래프를 만든다(마스터 지시 2026-11-22 "Chiip Industry 11·22 잘 만들었는데, 시각물이 부족하다.
시각물을 많이 만들어 가독성을 높여라").

11·22 주간(DRAM·HBM)은 표 25개·그래프 0개였다 — weekly_frame·quarter_frame이 gallery를 비워 두고 그래프를 하나도 만들지 않았다.
여기서는 새 숫자를 만들지 않는다. 데이터팩에 이미 있는 값만 그린다:
  segments(시장 반영 vs 기대) · logic.scenarios(확률·값) · logic.estimates(Chiip vs 컨센서스) · logic.revisions(상향·하향 건수)
  · logic.valuation_history(밴드 위치) · checkpoints(확률) · logic.drivers(물량·가격 변화) · logic.market_size(지금·전망 범위)
  + dp.charts — 모델이 본문 숫자로 직접 쓴 그래프(같은 report_html 차트 형식, "after": 그 표 제목 앞부분 또는 절 제목(h2), "gallery": true면 한눈에 보기).
place(sec, charts)가 그래프를 해당 표 바로 뒤에 꽂는다. 짝 표가 없으면 한눈에 보기로 간다.
그래프 제목에는 데이터 제공처 이름을 쓰지 않는다 — 렌더(report_html.scrub)가 지워 '(%, )'처럼 남는다(2026-11-22).
"""
MIN_CHARTS = 8   # 리포트 한 편의 그래프 하한 — 못 미치면 industry_html이 경고한다


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _hb(title, unit, rows, name=None):
    """rows = [(이름, 값, 색)] — 막대 이름은 하나로(범례에 항목이 줄줄이 나오지 않게)"""
    nm = name or title.split(" — ")[0].split("(")[0].strip()
    return {"kind": "hbars", "title": title, "unit": unit,
            "rows": [{"label": str(l), "bars": [{"name": nm, "color": c, "value": round(v, 1)}]} for l, v, c in rows if v is not None]}


def auto(dp, rows=None):
    """[(짝 표 제목 앞부분 또는 None, 차트)] — 데이터팩 구조화 숫자만"""
    L = dp.get("logic") or {}
    out = []
    seg = [r for r in (rows or []) if r.get("market") is not None and r.get("expected") is not None]
    if seg:
        out.append(("사업군 판단 등급", {"kind": "hbars", "title": "시장 반영 vs 제 기대 — 사업군별(%p)", "unit": "%p",
                                       "rows": [{"label": r["name"], "bars": [{"name": "시장 반영", "color": "b", "value": round(float(r["market"]), 1)},
                                                                             {"name": "제 기대", "color": "c", "value": round(float(r["expected"]), 1)}]} for r in seg]}))
    sc = [s for s in L.get("scenarios") or [] if _f(s.get("value")) is not None and _f(s.get("p")) is not None]
    if sc:
        ev = sum(_f(s["p"]) * _f(s["value"]) for s in sc)
        now = _f(((L.get("market_size") or {}).get("now") or {}).get("value"))
        col = {"약세": "b", "기본": "c", "강세": "a"}
        out.append(("시나리오", {"kind": "scenario", "title": f"시나리오 — {sc[0].get('kpi', '')}(확률 가중 {ev:,.0f})", "unit": "", "current": now,
                                "cases": [{"name": s.get("case"), "value": _f(s["value"]), "prob": _f(s["p"]), "color": col.get(s.get("case"), "e"), "why": s.get("assume", "")} for s in sc]}))
    es = [e for e in L.get("estimates") or [] if _f(e.get("chiip")) is not None and _f(e.get("street"))]
    if es:
        out.append(("Chiip 추정 vs 컨센서스", _hb("제 추정 − 컨센서스(%) — 차이가 곧 차별 견해", "%",
                                              [(f"{e.get('company')} {e.get('metric')}", (_f(e["chiip"]) / _f(e["street"]) - 1) * 100,
                                                "a" if _f(e["chiip"]) >= _f(e["street"]) else "b") for e in es])))
    rv = [r for r in L.get("revisions") or [] if _f(r.get("up")) is not None and _f(r.get("down")) is not None]
    if rv:
        out.append(("추정치 수정 폭", {"kind": "bars", "title": "추정치 수정 — 상향 vs 하향(건)", "unit": "건", "categories": [r.get("metric") for r in rv],
                                     "series": [{"name": "상향", "color": "a", "values": [_f(r["up"]) for r in rv]},
                                                {"name": "하향", "color": "b", "values": [_f(r["down"]) for r in rv]}]}))
    vh = [v for v in L.get("valuation_history") or [] if None not in (_f(v.get("now")), _f(v.get("low")), _f(v.get("high"))) and _f(v["high"]) > _f(v["low"])]
    if vh:
        out.append(("역사적 멀티플 밴드", _hb("멀티플 밴드 위치(%, 0=5년 저점·100=고점)", "%",
                                          [(f"{v.get('name')} {v.get('multiple')}", (_f(v["now"]) - _f(v["low"])) / (_f(v["high"]) - _f(v["low"])) * 100, "c") for v in vh])))
    dr = [x for x in L.get("drivers") or [] if _f((x.get("volume") or {}).get("chg")) is not None and _f((x.get("price") or {}).get("chg")) is not None]
    if dr:
        out.append(("동인 분해", {"kind": "bars", "title": "동인 분해 — 물량 vs 가격 변화(%)", "unit": "%", "categories": [x.get("name") for x in dr],
                                 "series": [{"name": (dr[0].get("volume") or {}).get("name") or "물량", "color": "d", "values": [_f(x["volume"]["chg"]) * 100 for x in dr]},
                                            {"name": (dr[0].get("price") or {}).get("name") or "가격", "color": "c", "values": [_f(x["price"]["chg"]) * 100 for x in dr]}]}))
    ms = L.get("market_size") or {}
    now, fc = (ms.get("now") or {}), [f for f in ms.get("forecast") or [] if _f(f.get("low")) is not None and _f(f.get("high")) is not None]
    if _f(now.get("value")) is not None and fc:
        cats = [str(now.get("year"))] + [str(f.get("year")) for f in fc]
        out.append(("시장 규모", {"kind": "bars", "title": "시장 규모 — 지금과 전망 범위", "unit": "", "categories": cats,
                                 "series": [{"name": "실적·하단", "color": "c", "values": [_f(now["value"])] + [_f(f["low"]) for f in fc]},
                                            {"name": "상단", "color": "e", "values": [None] + [_f(f["high"]) for f in fc]}]}))
    cp = [c for c in dp.get("checkpoints") or [] if _f(c.get("p")) is not None]
    if cp:
        out.append(("확인할 사건", _hb("확인할 사건 — 제 확률(%)", "%", [(f"{str(c.get('date'))[5:]} {c.get('what')}"[:60], _f(c["p"]) * 100, "c") for c in cp])))
    for c in dp.get("charts") or []:
        if c.get("kind"):
            out.append((None if c.get("gallery") else c.get("after"), {k: v for k, v in c.items() if k not in ("after", "gallery")}))
    return out


def place(sec, charts, gallery_max=0):
    """그래프를 짝 표 바로 뒤에 꽂고, 짝이 없거나 gallery로 표시한 것은 한눈에 보기 목록으로 돌려준다"""
    gal = []
    for after, c in charts:
        done = False
        if after:
            for s in sec:
                bl = s.get("blocks") or []
                for i, b in enumerate(bl):
                    if str(b.get("title") or "").startswith(after):
                        j = i + 1
                        while j < len(bl) and bl[j].get("type") == "chart":   # 같은 표 뒤 그래프는 순서대로
                            j += 1
                        bl.insert(j, {"type": "chart", "chart": c})
                        done = True
                        break
                if done:
                    break
            if not done:   # 표가 없는 절(서술만)은 절 제목(h2)으로 — 그 절 끝에
                for sct in sec:
                    if str(sct.get("h2") or "").startswith(after):
                        sct.setdefault("blocks", []).append({"type": "chart", "chart": c})
                        done = True
                        break
        if not done:
            gal.append(c)
    return gal[:gallery_max] if gallery_max else gal


def count(d):
    return len(d.get("gallery") or []) + sum(1 for s in d.get("sections") or [] for b in s.get("blocks") or [] if b.get("type") == "chart")
