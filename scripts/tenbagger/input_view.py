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
        return []
    B = [{"type": "table", "title": f"BOM 투입 물가 — PPI 전년비, {data.get('as_of')} 수집", "headers": ["항목", "미국", "일본", "한국", "대만"],
          "rows": [[name, _yoy(inputs[k], "us"), _yoy(inputs[k], "jp"), _yoy(inputs[k], "kr"), _yoy(inputs[k], "tw")] for k, name in items.items()]}]
    text = "별표는 품목보다 넓은 업종 지수다."
    drag, cover = pressure(dp, data)
    if drag is not None:
        text += f" 지난 1년 투입 물가를 판매가 전가 뒤 원가에 그대로 넣으면 OPM은 {drag * 100:+.2f}%p 움직인다(매출원가의 {cover * 100:.0f}% 기준)."
    B.append({"type": "p", "text": text})
    return B


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
