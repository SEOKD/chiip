"""리포트 투입 물가·무역 연결 (마스터 지시 2026-11-02 "BOM과 공급망 파악, 밸류에이션 계산할 때 … 무역 지표의 세부항목 데이터와 PPI의 세부항목 데이터를 가져오도록")

BOM 항목·공급 품목에 "input": "<config/trade_ppi.yaml inputs 키>"를 쓰면 radar/trade_ppi.py가 모은 값을 붙인다.
- 마진 구조: 품목별 PPI 전년비와 EU 수입처, 지난 1년 물가를 판매가 전가 뒤 원가에 반영한 OPM 압력
- 공급망 병목: EU·일본 수입처(세계 공급 집중의 근사)
- 밸류에이션: OPM 압력 한 줄. 동인을 자동으로 바꾸지 않는다 — 크면 모델이 datapack overrides에 이유와 함께 반영한다
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import margin_view  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LATEST = ROOT / "knowledge" / "models" / "trade_ppi" / "latest.json"
UNKNOWN = "미확인"


def load(path=LATEST):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def price_move(v):
    """품목 세부 지수의 평균 전년비. 세부 지수가 없을 때만 업종 대용을 쓴다"""
    rows = [(c, m["yoy"]) for c, m in (v.get("ppi") or {}).items() if m and m.get("yoy") is not None]
    exact = [y for c, y in rows if c not in (v.get("proxy") or [])]
    use = exact or [y for _, y in rows]
    return sum(use) / len(use) if use else None


def _pct(x):
    return UNKNOWN if x is None else f"{x * 100:+.1f}%"


def _yoy(v, c):
    m = (v.get("ppi") or {}).get(c)
    return _pct(m.get("yoy") if m else None) + ("*" if c in (v.get("proxy") or []) else "")


def sources(v):
    return sorted(((v.get("trade") or {}).get("eu") or {}).get("partners", {}).items(), key=lambda kv: -kv[1]["value"])


def _top(v):
    rows = sources(v)
    return f"{rows[0][0]} {rows[0][1]['share'] * 100:.0f}%" if rows and rows[0][1].get("share") else UNKNOWN


def pressure(dp, data):
    """지난 1년 물가를 판매가 전가 뒤 원가에 넣은 OPM 변화 — 항목별 합, (OPM 변화, 덮은 매출원가 몫)"""
    c = margin_view.compute(dp)
    inputs, total, hit = data.get("inputs", {}), 0.0, 0.0
    for r in c["items"]:
        move = price_move(inputs[r["input"]]) if r.get("input") in inputs else None
        if move is None or r["cost_weight"] is None:
            continue
        total -= r["cost_weight"] * move * (1 - (r["passed"] or 0))
        hit += r["cost_weight"]
    return (total, hit / (1 - c["now"]["gpm"])) if hit else (None, 0.0)


def check(dp, data=None):
    known = (data or load()).get("inputs")
    if not known:
        return
    tags = [b.get("input") for p in dp["margin"]["products"] for b in p["bom"]] + [x.get("input") for x in (dp.get("supply") or {}).get("links") or []]
    bad = sorted({t for t in tags if t and t not in known})
    if bad:
        raise ValueError(f"config/trade_ppi.yaml inputs에 없는 input: {bad}")


def margin_blocks(dp, data=None):
    data = data if data is not None else load()
    inputs = data.get("inputs", {})
    check(dp, data)
    items = {b["input"]: b["item"] for p in dp["margin"]["products"] for b in p["bom"] if b.get("input") in inputs}
    if not items:
        return pricing_blocks(dp)   # BOM 연결이 없어도 비용 요인·판매가 물가는 본다(2026-11-13)
    B = [{"type": "table", "title": f"BOM 투입 물가 — PPI 전년비, {data.get('as_of')} 수집", "headers": ["항목", "미국", "일본", "한국", "대만"],
          "rows": [[name, _yoy(inputs[k], "us"), _yoy(inputs[k], "jp"), _yoy(inputs[k], "kr"), _yoy(inputs[k], "tw")] for k, name in items.items()]}]
    text = "별표는 품목보다 넓은 업종 지수다."
    drag, cover = pressure(dp, data)
    if drag is not None:
        text += f" 지난 1년 투입 물가를 판매가 전가 뒤 원가에 그대로 넣으면 OPM은 {drag * 100:+.2f}%p 움직인다(매출원가의 {cover * 100:.0f}% 기준)."
    B.append({"type": "p", "text": text})
    return B + pricing_blocks(dp)


def _route(v, kind):
    """대만 수출처·일본 수입처 상위 2곳"""
    rows = sorted(((v.get("trade") or {}).get(kind) or {}).get("partners", {}).items(), key=lambda kv: -kv[1]["value"])[:2]
    return " · ".join(f"{c} {m['share'] * 100:.0f}%" for c, m in rows) or UNKNOWN


def supply_blocks(dp, data=None):
    data = data if data is not None else load()
    inputs = data.get("inputs", {})
    rows = []
    for x in (dp.get("supply") or {}).get("links") or []:
        v = inputs.get(x.get("input"))
        if v and sources(v):
            rows.append([x["item"], " · ".join(f"{c} {m['share'] * 100:.0f}%" for c, m in sources(v)[:3]), _route(v, "jp"), _pct(sources(v)[0][1].get("yoy"))])
    return [{"type": "table", "title": "무역 통계로 본 공급 지역", "headers": ["품목", "EU 수입처", "일본 수입처", "EU 1위 전년비"], "rows": rows}] if rows else []


def valuation_line(dp, data=None):
    drag, cover = pressure(dp, data if data is not None else load())
    if drag is None:
        return None
    return {"type": "p", "text": f"투입 물가 점검: 지난 1년 PPI를 BOM에 넣으면 OPM {drag * 100:+.2f}%p다(매출원가의 {cover * 100:.0f}% 기준)."}


# ── 원가·판매가 물가 다리(마스터 지시 2026-11-13 "CPI·PPI를 Analysis에 활용", ADR-030) ──────────────────────
# 원가 쪽: margin.costs·BOM 항목의 input(config/trade_ppi.yaml)을 미국 PPI 이력(history.json, 개정 반영)에 붙여 3·6·12개월 변화와
#          '전가하지 못하면' GPM·OPM이 얼마나 움직이나(매출 대비 비용 몫 × 물가 변화). 연결 못 한 매출원가 항목은 '미연결'로 남긴다.
# 판매가 쪽: datapack "pricing": [{"business": 사업, "index": "cpi:<BLS id>" | "ppi:<input 키>" | "ppi_id:<BLS id>",
#            "company": {"yoy": 회사 가격 변화(평균 회비·ASP 등), "basis": "출처"}}] — 회사 가격 변화 − 지수 변화 = 가격 결정력,
#          판매가 지수 − 원가 가중 PPI = 원가·판매가 물가 격차. 숫자는 여기서 계산하고 모델은 원자료만 쓴다.
HIST = ROOT / "knowledge" / "models" / "trade_ppi" / "history.json"
CPI = ROOT / "knowledge" / "models" / "macro" / "cpi.json"
SPREAD_FLAG = 0.02   # 원가·판매가 물가 격차가 2%p 이상이면 절 맨 위 한 줄(마스터 지시 '중요할 때만')


def _json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except (OSError, ValueError):
        return {}


def series(ref, hist=None, cpi=None):
    """'ppi:<input>'·'ppi_id:<id>'·'cpi:<id>' → {YYYY-MM: 값}"""
    hist = hist if hist is not None else _json(HIST)
    cpi = cpi if cpi is not None else _json(CPI)
    kind, _, key = str(ref or "").partition(":")
    if kind == "ppi":
        return ((hist.get("inputs") or {}).get(key) or {}).get("ppi", {}).get("us") or {}
    if kind == "ppi_id":
        return (hist.get("us_raw") or {}).get(key) or {}
    if kind == "cpi":
        return (cpi.get("raw") or {}).get(key) or {}
    return {}


def _back(month, n):
    y, m = int(month[:4]), int(month[5:7]) - n
    while m <= 0:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


def change(s, n, step_back=2):
    """마지막 달 대비 n개월 전 변화와 기준 달 — 짝이 없으면(예: 2025-10 CPI 미발표) 최근 step_back개월 안에서 짝이 있는 달로 물러난다. 끝내 없으면 None"""
    if not s:
        return None, None
    for k in range(step_back + 1):
        last = _back(max(s), k)
        prev = s.get(_back(last, n))
        if s.get(last) and prev:
            return s[last] / prev - 1, last
    return None, max(s)


def cost_rows(dp, hist=None):
    """[{name, stage, pct_rev, ch3, ch6, ch12, month, d_gpm, d_opm}] + 미연결 매출원가 항목 이름"""
    hist = hist if hist is not None else _json(HIST)
    rows, unmapped = [], []
    for c in (dp.get("margin") or {}).get("costs") or []:
        pct = c.get("pct_rev") if isinstance(c.get("pct_rev"), (int, float)) else None
        s = series(f"ppi:{c['input']}", hist) if c.get("input") else {}
        if not s:
            if c.get("stage") == "매출원가" and not str(c.get("name", "")).startswith("기타"):
                unmapped.append(c.get("name"))
            continue
        ch = {n: change(s, n)[0] for n in (3, 6, 12)}
        hit = -pct * ch[12] if pct is not None and ch[12] is not None else None   # 전가 0% 가정
        rows.append({"name": c["name"], "stage": c.get("stage"), "pct_rev": pct, "ch3": ch[3], "ch6": ch[6], "ch12": ch[12], "month": max(s),
                     "d_gpm": hit if c.get("stage") == "매출원가" else 0.0, "d_opm": hit})
    return rows, unmapped


def price_rows(dp, hist=None, cpi=None):
    out = []
    for p in dp.get("pricing") or []:
        s = series(p.get("index"), hist, cpi)
        y, m = change(s, 12)
        comp = (p.get("company") or {}).get("yoy")
        out.append({"business": p.get("business"), "index": p.get("index"), "label": p.get("label") or p.get("index"), "idx12": y, "month": m,
                    "company": comp, "basis": (p.get("company") or {}).get("basis"), "power": comp - y if None not in (comp, y) else None})
    return out


def bridge(dp, hist=None, cpi=None):
    costs, unmapped = cost_rows(dp, hist)
    prices = price_rows(dp, hist, cpi)
    w = [(r["pct_rev"], r["ch12"]) for r in costs if r["pct_rev"] and r["ch12"] is not None]
    cost12 = sum(a * b for a, b in w) / sum(a for a, _ in w) if w else None
    out12 = [r["idx12"] for r in prices if r["idx12"] is not None]
    out12 = sum(out12) / len(out12) if out12 else None
    return {"costs": costs, "unmapped": unmapped, "prices": prices, "cost12": cost12, "out12": out12,
            "spread": out12 - cost12 if None not in (out12, cost12) else None,
            "d_gpm": sum(r["d_gpm"] or 0 for r in costs) if costs else None, "d_opm": sum(r["d_opm"] or 0 for r in costs) if costs else None}


def pricing_blocks(dp, hist=None, cpi=None):
    """마진 구조 절의 원가·판매가 물가 한두 문장 + 작은 그림 + 표. 재료가 없으면 []"""
    b = bridge(dp, hist, cpi)
    if not b["costs"] and not b["prices"]:
        return []
    pc = lambda x: UNKNOWN if x is None else f"{x * 100:+.1f}%"
    pp = lambda x: UNKNOWN if x is None else f"{x * 100:+.1f}%p"
    months = sorted({r["month"] for r in b["costs"] + b["prices"] if r.get("month")})
    asof = months[-1] if months else UNKNOWN
    say = []
    if b["cost12"] is not None:
        say.append(f"연결한 투입 원가의 미국 PPI는 1년 새 가중 {pc(b['cost12'])}이고, 판매가로 넘기지 못하면 GPM {pp(b['d_gpm'])}·OPM {pp(b['d_opm'])}가 움직인다")
    pw = [r for r in b["prices"] if r["power"] is not None]
    if pw:
        r = pw[0]
        say.append(f"{r['business']} 가격은 {pc(r['company'])}로 비교 물가({r['label']}, {r['month']}) {pc(r['idx12'])}보다 {abs(r['power']) * 100:.1f}%p {'더' if r['power'] >= 0 else '덜'} 올랐다")
    elif b["prices"]:
        r = b["prices"][0]
        say.append(f"판매가 비교 물가({r['label']})는 1년 새 {pc(r['idx12'])}" + ("" if r["idx12"] is not None else "(전년 같은 달 값 없음)") + " — 회사 가격 변화는 미확인")
    B = []
    if b["spread"] is not None and abs(b["spread"]) >= SPREAD_FLAG:
        B.append({"type": "hl", "text": f"**원가·판매가 물가 격차 {pp(b['spread'])}** — 판매가 물가가 투입 원가 물가보다 {'빠르게' if b['spread'] > 0 else '느리게'} 오른다({asof} 기준)."})
    B.append({"type": "p", "text": "**물가로 본 가격 결정력(" + asof + " 기준, 개정 반영):** " + ". ".join(say) + "." + (f" 물가 지수를 붙이지 못한 매출원가 항목: {', '.join(b['unmapped'])}(미연결)." if b["unmapped"] else "")})
    bars = [{"label": f"원가 PPI({r['name']})", "bars": [{"name": "1년 변화", "color": "b" if (r["ch12"] or 0) > 0 else "d", "value": round(r["ch12"] * 100, 1)}]} for r in b["costs"] if r["ch12"] is not None]
    for r in b["prices"]:
        if r["idx12"] is not None:
            bars.append({"label": f"판매가 지수({r['label']})", "bars": [{"name": "1년 변화", "color": "c", "value": round(r["idx12"] * 100, 1)}]})
        if r["company"] is not None:
            bars.append({"label": f"회사 가격({r['business']})", "bars": [{"name": "1년 변화", "color": "a", "value": round(r["company"] * 100, 1)}]})
    if bars:
        B.append({"type": "chart", "chart": {"kind": "hbars", "w": 480, "label_w": 170, "title": f"투입 원가 물가·판매가 물가·회사 가격 — 1년 변화({asof})", "unit": "%", "rows": bars}})
    if b["costs"]:
        B.append({"type": "table", "title": f"투입 원가 PPI 변화와 전가 못 할 때 마진 영향({asof}, 미국)", "headers": ["비용", "매출 대비", "3개월", "6개월", "12개월", "GPM", "OPM"],
                  "rows": [[r["name"], pc(r["pct_rev"]).lstrip("+"), pc(r["ch3"]), pc(r["ch6"]), pc(r["ch12"]), pp(r["d_gpm"]), pp(r["d_opm"])] for r in b["costs"]]})
    return B
