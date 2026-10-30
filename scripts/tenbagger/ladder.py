"""텐배거 리포트 '배수 사다리' 절 (마스터 지시 2026-10-30 "10배가 되려면?을 시가총액 $30B 미만인 경우만 최대 10배(2배, 3배, 5배, 10배로 나누어라)가
되려면 어떻게 성장하고 펀더멘털 전망이 어떠한지 분석하고, $30B~$100B 사이는 최대 5배, $100B 이상은 최대 2배로")

시가총액으로 단계를 정하고(config/tenbagger.yaml ladder), 단계마다 숫자는 여기서 계산한다 — 모델은 datapack "ladder"에 출구 가정과 단계별 글만 쓴다.
  목표 시가총액 → 필요 순이익(출구 P/E) → 필요 매출(출구 순이익률) → 지금 매출 대비·참조 시장 점유 → 5·10년 매출 CAGR
  + DCF 역산 필요 CAGR과 기저율(v2 upside.required) + 5년 뒤 가치 ≥ k배 확률(몬테카를로 p_h)
datapack "ladder":
  {"exit": {"pe": 15, "net_margin": 0.075, "basis": "왜 이 가정인가"} 또는 {"ev_sales": 5, "basis": …},
   "market": {"name": "WFE", "size": 235, "basis": "…"},          # 선택 — 필요 매출의 점유율(단위는 리포트 단위)
   "refs": [{"label": "FY2027 추정", "value": 3.75}, …],           # 선택 — 그래프의 기준 막대
   "steps": {"2": {"verdict": "열림|조건부|닫힘", "path": "어떻게 성장해야 하나", "outlook": "펀더멘털 전망"}, …},   # 시가총액 구간의 단계 전부
   "summary": "요약에 붙일 한 문장"}
단계가 빠지면 ValueError — 예약 회차가 옛 '10배 경로' 양식으로 돌아가지 않게 한다.
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from units import money_units  # noqa: E402


def tiers():
    return yaml.safe_load((ROOT / "config" / "tenbagger.yaml").read_text(encoding="utf-8"))["ladder"]["tiers"]


def steps_for(mcap_usd, tier_list=None):
    """시가총액(달러) → 볼 배수 목록. $30B 미만 2·3·5·10, $30B~$100B 2·3·5, $100B 이상 2"""
    for t in tier_list or tiers():
        if t.get("max_usd") is None or mcap_usd < float(t["max_usd"]):
            return list(t["steps"])
    raise ValueError("config/tenbagger.yaml ladder.tiers 마지막 구간은 max_usd: null 이어야 한다")


def label(steps):
    return "·".join(f"{k}" for k in steps) + "배"


def _money(v, unit):
    return money_units(f"{v:,.2f} {unit}" if v < 100 else f"{v:,.0f} {unit}")


def _cagr(need, base, years):
    return (need / base) ** (1 / years) - 1 if need > 0 and base > 0 else None


def _pct(x, nd=1):
    return "-" if x is None else f"{x * 100:.{nd}f}%"


def compute(dp, co, r):
    """단계별 숫자 — 금액 단위는 리포트 단위(보통 B$)"""
    lad = (dp or {}).get("ladder") or {}
    ex = lad.get("exit") or {}
    if not (ex.get("ev_sales") or (ex.get("pe") and ex.get("net_margin"))):
        raise ValueError("datapack ladder.exit에 pe·net_margin 또는 ev_sales가 필요하다")
    mcap, rev0 = r["mcap"], co["rev0"]
    u = r["upside"]
    net_debt = co["market"].get("net_debt") or 0
    mkt = lad.get("market") or {}
    rows = []
    for k in steps_for(mcap * float(co.get("unit_usd", 1e9))):
        target = k * mcap
        if ex.get("ev_sales"):
            profit, need = None, (target + net_debt) / ex["ev_sales"]
        else:
            profit = target / ex["pe"]
            need = profit / ex["net_margin"]
        rc, pct = (u.get("required") or {}).get(k, (None, None))
        rows.append({"k": k, "target": target, "profit": profit, "rev": need, "vs_rev0": need / rev0,
                     "cagr5": _cagr(need, rev0, 5), "cagr10": _cagr(need, rev0, 10),
                     "share": need / mkt["size"] if mkt.get("size") else None,
                     "dcf_cagr": rc, "pctile": (pct or (None,))[0], "n": (pct or (None, 0))[1],
                     "prob": (u.get("p_h") or {}).get(k)})
    return {"rows": rows, "steps": [x["k"] for x in rows], "mcap": mcap, "rev0": rev0, "unit": r["unit"], "exit": ex, "market": mkt}


def _check_text(lad, steps):
    have = lad.get("steps") or {}
    miss = [k for k in steps if not (have.get(str(k)) or {}).get("path") or not (have.get(str(k)) or {}).get("outlook")]
    if miss:
        raise ValueError(f"datapack ladder.steps에 {miss}배의 path·outlook이 없다 — 시가총액 구간 단계 {steps} 전부 필요")


def report_section(dp, co, r):
    lad = (dp or {}).get("ladder")
    if not lad:
        return None
    c = compute(dp, co, r)
    _check_text(lad, c["steps"])
    unit, ex, mkt = c["unit"], c["exit"], c["market"]
    txt = lad["steps"]
    basis = ex.get("basis", "")
    assume = f"출구 P/E {ex['pe']:g}배·순이익률 {ex['net_margin']:.1%}" if ex.get("pe") else f"출구 EV/매출 {ex['ev_sales']:g}배"
    B = [{"type": "hl", "text": f"**시가총액 {_money(c['mcap'], unit)} → {label(c['steps'])}까지 본다.** 시가총액이 커질수록 볼 배수를 줄인다($30B 미만 10배, $30B~$100B 5배, $100B 이상 2배까지). "
                                f"숫자는 {assume} 기준이다. {basis}".strip()}]
    head = ["배수", "목표 시가총액", "필요 매출", "지금 매출 대비", "매출 CAGR 5년 / 10년", "DCF 역산 5년 CAGR", "5년 뒤 확률", "판정"]
    rows = []
    for x in c["rows"]:
        tail = f"(상위 {100 - x['pctile']:.0f}%, n={x['n']})" if x.get("pctile") is not None else ""
        rows.append([f"**{x['k']}배**", _money(x["target"], unit), _money(x["rev"], unit), f"{x['vs_rev0']:.1f}배", f"{_pct(x['cagr5'])} / {_pct(x['cagr10'])}",
                     f"{_pct(x['dcf_cagr'])} {tail}".strip(), _pct(x["prob"], 0), txt[str(x["k"])].get("verdict", "")])
    note = "지금 매출 = 기준연도 매출 " + _money(c["rev0"], unit) + ". 5년 뒤 확률 = 몬테카를로에서 5년 뒤 주주가치가 지금 시가총액의 k배 이상인 비율(할인 전). 기저율 = 같은 매출 규모 미국 상장사가 실제로 달성한 5년 CAGR 분포."
    if mkt.get("size"):
        rows = [row[:4] + [f"{x['share'] * 100:.1f}%"] + row[4:] for row, x in zip(rows, c["rows"])]
        head = head[:4] + [f"{mkt.get('name', '참조 시장')} 점유"] + head[4:]
        note += f" 점유 기준 {mkt.get('name', '참조 시장')} {_money(mkt['size'], unit)}" + (f" — {mkt['basis']}" if mkt.get("basis") else "")
    B.append({"type": "table", "title": f"배수 단계별 필요 조건 — {label(c['steps'])}", "headers": head, "rows": rows, "note": note})
    bars = [{"label": a["label"], "bars": [{"name": "회사 경로·추정", "color": "c", "value": a["value"]}]} for a in lad.get("refs") or []]
    bars += [{"label": f"{x['k']}배에 필요한 매출", "bars": [{"name": "필요 매출", "color": "b", "value": round(x["rev"], 2)}]} for x in c["rows"]]
    if bars:
        B.append({"type": "chart", "chart": {"kind": "hbars", "pin": 9, "w": 480, "label_w": 150, "title": f"배수 단계별 필요 매출 vs 회사 경로 ({unit})", "unit": f" {unit}", "rows": bars}})
    for x in c["rows"]:
        s = txt[str(x["k"])]
        B.append({"type": "h3", "text": f"{x['k']}배 — {_money(x['target'], unit)}" + (f" · {s['verdict']}" if s.get("verdict") else "")})
        B.append({"type": "ul", "items": [f"**어떻게 성장해야 하나:** {s['path']}", f"**펀더멘털 전망:** {s['outlook']}"]})
    return {"h2": f"배수 사다리 — {label(c['steps'])}가 되려면", "blocks": B}


def summary_item(dp, co, r):
    lad = (dp or {}).get("ladder") or {}
    c = compute(dp, co, r)
    unit = c["unit"]
    parts = []
    for x in c["rows"]:
        v = (lad.get("steps") or {}).get(str(x["k"]), {}).get("verdict", "")
        parts.append(f"**{x['k']}배** 시가총액 {_money(x['target'], unit)} = 매출 {_money(x['rev'], unit)}(5년 CAGR {_pct(x['cagr5'], 0)}, 5년 뒤 확률 {_pct(x['prob'], 0)}" + (f", {v}" if v else "") + ")")
    return {"q": f"{label(c['steps'])}가 되려면?", "a": " · ".join(parts) + (f". {lad['summary']}" if lad.get("summary") else ""), "auto": True}
