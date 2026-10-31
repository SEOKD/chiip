"""텐배거 리포트 '배수 사다리' 절 (마스터 지시 2026-10-30 "10배가 되려면?을 시가총액 $30B 미만인 경우만 최대 10배(2배, 3배, 5배, 10배로 나누어라)가
되려면 어떻게 성장하고 펀더멘털 전망이 어떠한지 분석하고, $30B~$100B 사이는 최대 5배, $100B 이상은 최대 2배로")

시가총액으로 단계를 정하고(config/tenbagger.yaml ladder), 단계마다 숫자는 여기서 계산한다 — 모델은 datapack "ladder"에 출구 가정과 단계별 글만 쓴다.
  목표 시가총액 → 필요 순이익(출구 P/E) 또는 필요 EBITDA(출구 EV/EBITDA) → 필요 매출 → 지금 매출 대비·참조 시장 점유 → 5·10년 매출 CAGR
  → 필요 이익률(OPM, 또는 회사 주요 지표인 EBITDA·EBITA Margin) → 필요 EPS(필요 순이익 ÷ 주식 수) → 5·10년 EPS CAGR(마스터 지시 2026-10-31)
  + DCF 역산 필요 CAGR과 기저율(v2 upside.required) + 5년 뒤 가치 ≥ k배 확률(몬테카를로 p_h)
datapack "ladder":
  {"exit": {"pe": 15, "net_margin": 0.075, "opm": 0.10, "basis": "왜 이 가정인가"}
           또는 {"ev_ebitda": 12, "ebitda_margin": 0.35, "net_margin": 0.12, "basis": …} 또는 {"ev_sales": 5, "net_margin": …, "opm": …, "basis": …},
                                                                     # opm·ebitda_margin·ebita_margin 중 하나 + net_margin 필수. shares(선택) = 출구 주식 수(희석 반영)
   "base": {"eps": 3.2, "opm": 0.06, "basis": "TTM 조정",            # 선택 — 없으면 EPS는 최근 4개 분기 consensus.surprise 합, OPM은 기본 시나리오 m0
            "cagr_from": {"eps": 0.49, "year": 1, "label": "FY2027 컨센서스"}},   # 선택 — 기준 EPS가 적자면 첫 흑자 해(기준연도 + year)에서 남은 기간으로 EPS CAGR을 잰다
   "market": {"name": "WFE", "size": 235, "basis": "…"},          # 선택 — 필요 매출의 점유율(단위는 리포트 단위)
   "refs": [{"label": "FY2027 추정", "value": 3.75}, …],           # 선택 — 그래프의 기준 막대
   "steps": {"2": {"verdict": "열림|조건부|닫힘", "path": "어떻게 성장해야 하나", "outlook": "펀더멘털 전망", "exit": {…}}, …},   # 시가총액 구간의 단계 전부. exit(선택) = 이 단계만 다른 출구 가정
   "summary": "요약에 붙일 한 문장"}
단계나 이익률이 빠지면 ValueError — 예약 회차가 옛 양식으로 돌아가지 않게 한다(옛 리포트 정정은 strict=False, `v2_to_report --legacy`).
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


MARGINS = (("opm", "OPM"), ("ebitda_margin", "EBITDA Margin"), ("ebita_margin", "EBITA Margin"))


def _margin(ex):
    """출구 가정의 이익률 지표 — (키, 표기, 값). 없으면 (None, 'OPM', None)"""
    for key, name in MARGINS:
        if ex.get(key) is not None:
            return key, name, ex[key]
    return None, "OPM", None


def _eps(v, unit):
    if v is None:
        return "미확인"
    if "$" in unit:
        return f"−${-v:,.2f}" if v < 0 else f"${v:,.2f}"
    return f"{v:,.0f}" + ("원" if "원" in unit else "엔" if "엔" in unit else "")


def base_eps(dp):
    """기준 EPS — ladder.base.eps, 없으면 최근 4개 분기 실제 EPS 합(분기가 모자라면 None)"""
    b = ((dp or {}).get("ladder") or {}).get("base") or {}
    if b.get("eps") is not None:
        return b["eps"]
    rows = [x for x in ((dp or {}).get("consensus") or {}).get("surprise") or [] if x.get("metric") == "EPS" and x.get("actual") is not None]
    rows = sorted(rows, key=lambda x: str(x.get("period")))[-4:]
    return sum(x["actual"] for x in rows) if len(rows) == 4 else None


def _required(ex, target, net_debt):
    """목표 시가총액 → (필요 매출, 필요 순이익) — 출구 P/E > EV/EBITDA > EV/매출 순서"""
    nm = ex.get("net_margin")
    if ex.get("pe") and nm:
        return target / ex["pe"] / nm, target / ex["pe"]
    if ex.get("ev_ebitda") and ex.get("ebitda_margin"):
        rev = (target + net_debt) / ex["ev_ebitda"] / ex["ebitda_margin"]
    elif ex.get("ev_sales"):
        rev = (target + net_debt) / ex["ev_sales"]
    else:
        raise ValueError("datapack ladder.exit에 pe·net_margin, ev_ebitda·ebitda_margin, ev_sales 중 하나가 필요하다")
    return rev, rev * nm if nm else None


def compute(dp, co, r, strict=True):
    """단계별 숫자 — 금액 단위는 리포트 단위(보통 B$). strict면 이익률·순이익률이 없을 때 멈춘다"""
    lad = (dp or {}).get("ladder") or {}
    ex0 = lad.get("exit") or {}
    mcap, rev0 = r["mcap"], co["rev0"]
    u = r["upside"]
    net_debt = co["market"].get("net_debt") or 0
    shares = co["market"].get("shares")
    mkt = lad.get("market") or {}
    eps0 = base_eps(dp)
    start = (lad.get("base") or {}).get("cagr_from") or {}
    e_base, e_year = (start.get("eps"), start.get("year", 0)) if eps0 is not None and eps0 <= 0 and start.get("eps") else (eps0, 0)
    texts = lad.get("steps") or {}
    rows = []
    for k in steps_for(mcap * float(co.get("unit_usd", 1e9))):
        ex = {**ex0, **((texts.get(str(k)) or {}).get("exit") or {})}
        name, margin = _margin(ex)[1:]
        if strict and (margin is None or not ex.get("net_margin")):
            raise ValueError(f"datapack ladder.exit에 opm(또는 ebitda_margin·ebita_margin)과 net_margin이 없다({k}배) — 옛 리포트 정정은 --legacy")
        target = k * mcap
        need, profit = _required(ex, target, net_debt)
        n_sh = ex.get("shares") or shares
        eps = profit / n_sh if profit and n_sh else None
        rc, pct = (u.get("required") or {}).get(k, (None, None))
        rows.append({"k": k, "target": target, "profit": profit, "rev": need, "vs_rev0": need / rev0,
                     "cagr5": _cagr(need, rev0, 5), "cagr10": _cagr(need, rev0, 10),
                     "margin": margin, "margin_name": name, "eps": eps,
                     "eps_cagr5": _cagr(eps, e_base, 5 - e_year) if eps and e_base else None, "eps_cagr10": _cagr(eps, e_base, 10 - e_year) if eps and e_base else None,
                     "share": need / mkt["size"] if mkt.get("size") else None,
                     "dcf_cagr": rc, "pctile": (pct or (None,))[0], "n": (pct or (None, 0))[1],
                     "prob": (u.get("p_h") or {}).get(k)})
    key = _margin(ex0)[0] or "opm"
    margin0 = (lad.get("base") or {}).get(key)
    if margin0 is None and key == "opm":
        margin0 = (((co.get("scenarios") or {}).get("base") or {}).get("margin") or {}).get("m0")
    return {"rows": rows, "steps": [x["k"] for x in rows], "mcap": mcap, "rev0": rev0, "unit": r["unit"], "exit": ex0, "market": mkt,
            "eps0": eps0, "margin0": margin0, "margin_name": dict(MARGINS)[key], "eps_from": start if e_year else None}


def _check_text(lad, steps):
    have = lad.get("steps") or {}
    miss = [k for k in steps if not (have.get(str(k)) or {}).get("path") or not (have.get(str(k)) or {}).get("outlook")]
    if miss:
        raise ValueError(f"datapack ladder.steps에 {miss}배의 path·outlook이 없다 — 시가총액 구간 단계 {steps} 전부 필요")


def mc_conclusion(n, p_h, steps):
    """몬테카를로 그림 아래 결론 한 줄 — 몇 번 돌려야 k배가 나오나(마스터 지시 2026-10-30 "부가 설명은 결론만"). 배수는 시가총액 구간 단계"""
    parts = []
    for k in steps:
        hits = round((p_h.get(k) or 0) * n)
        if hits:
            parts.append(f"{k}배 이상 {hits:,}번(약 {n / hits:.1f}번에 1번)" if n / hits < 10 else f"{k}배 이상 {hits:,}번(약 {n / hits:.0f}번에 1번)")
        else:
            parts.append(f"{k}배 이상 0번")
    return f"{n:,}번 돌리면 5년 뒤 주주가치가 지금 시가총액의 " + " · ".join(parts)


def mc_reading(n, above, p10, p50, p90, p_h, steps):
    """몬테카를로 그림 아래 해석(마스터 지시 2026-10-30 "그래프만 보고 직관적으로 안 다가오니 이 그림에만 해석을 넣어라").
    above = 지금 가치 ≥ 지금 시가총액인 비율, p10·p50·p90 = 지금 가치 ÷ 시가총액. 숫자는 시뮬레이션에서 그대로, 문장만 규칙으로 고른다"""
    if above >= 0.6:
        read = "가정을 흔들어도 지금 주가를 뒷받침하는 경우가 더 많다"
    elif above >= 0.4:
        read = "지금 주가를 뒷받침하는 경우와 그렇지 않은 경우가 반반에 가깝다"
    else:
        read = "가정을 흔들어도 지금 주가를 뒷받침하지 못하는 경우가 더 많다"
    return [f"읽는 법: 성장률·이익률·재투자·할인율 가정을 무작위로 바꿔 회사 가치를 {n:,}번 계산했다. 가로축은 그 가치가 지금 시가총액의 몇 배인지, 막대 높이는 그 값이 얼마나 자주 나왔는지를 뜻한다. 1.00이 지금 주가다.",
            f"해석: {n:,}번 중 {round(above * n):,}번({above:.0%})에서 가치가 지금 주가 이상이었다. {read}. 가운데 값은 {p50:.2f}배이고, 열 번 중 여덟 번은 {p10:.2f}~{p90:.2f}배 사이에 든다.",
            mc_conclusion(n, p_h, steps)]


def _cagr_text(v, need):
    return _pct(v) if v is not None else ("기준 적자·미확인" if need else "미확인")


def _need_line(x, unit):
    """단계별 필요 조건 한 줄 — 매출·이익률·EPS의 규모와 5년 CAGR"""
    m = f"{x['margin_name']} {_pct(x['margin'])}" if x["margin"] is not None else f"{x['margin_name']} 미확인"
    return f"매출 {_money(x['rev'], unit)}(5년 CAGR {_pct(x['cagr5'])}) · {m} · EPS {_eps(x['eps'], unit)}(5년 CAGR {_cagr_text(x['eps_cagr5'], x['eps'])})"


def report_section(dp, co, r, strict=True):
    lad = (dp or {}).get("ladder")
    if not lad:
        return None
    c = compute(dp, co, r, strict)
    _check_text(lad, c["steps"])
    unit, ex, mkt = c["unit"], c["exit"], c["market"]
    txt = lad["steps"]
    basis = ex.get("basis", "")
    head_multiple = f"출구 P/E {ex['pe']:g}배" if ex.get("pe") else f"출구 EV/EBITDA {ex['ev_ebitda']:g}배" if ex.get("ev_ebitda") else f"출구 EV/매출 {ex['ev_sales']:g}배"
    m0 = _margin(ex)[2]
    assume = "·".join(x for x in (head_multiple, f"{c['margin_name']} {m0:.1%}" if m0 is not None else "", f"순이익률 {ex['net_margin']:.1%}" if ex.get("net_margin") else "") if x)
    B = [{"type": "hl", "text": f"**시가총액 {_money(c['mcap'], unit)} → {label(c['steps'])}까지 본다.** 시가총액이 커질수록 볼 배수를 줄인다($30B 미만 10배, $30B~$100B 5배, $100B 이상 2배까지). "
                                f"숫자는 {assume} 기준이다. {basis}".strip()
                                + (f" 기준 EPS가 적자라 EPS CAGR은 {c['eps_from'].get('label', '첫 흑자 해')} {_eps(c['eps_from']['eps'], unit)}에서 잰다." if c.get("eps_from") else "")}]
    # 필요 조건 표(마스터 지시 2026-10-31 "매출 규모 및 CAGR뿐 아니라 OPM(또는 EBITDA Margin), EPS 규모 및 CAGR까지")
    need_rows = [["**지금**", _money(c["mcap"], unit), _money(c["rev0"], unit), "-", _pct(c["margin0"]) if c["margin0"] is not None else "미확인", _eps(c["eps0"], unit), "-"]]
    for x in c["rows"]:
        need_rows.append([f"**{x['k']}배**", _money(x["target"], unit), _money(x["rev"], unit), f"{_pct(x['cagr5'])} / {_pct(x['cagr10'])}",
                          _pct(x["margin"]) if x["margin"] is not None else "미확인", _eps(x["eps"], unit),
                          f"{_cagr_text(x['eps_cagr5'], x['eps'])} / {_cagr_text(x['eps_cagr10'], x['eps'])}"])
    B.append({"type": "table", "title": f"배수 단계별 필요 조건 — {label(c['steps'])}",
              "headers": ["배수", "목표 시가총액", "필요 매출", "매출 CAGR 5년 / 10년", c["margin_name"], "필요 EPS", "EPS CAGR 5년 / 10년"], "rows": need_rows})
    head = ["배수", "지금 매출 대비", "DCF 역산 5년 CAGR", "5년 뒤 확률", "판정"]
    rows = []
    for x in c["rows"]:
        tail = f"(상위 {100 - x['pctile']:.0f}%, n={x['n']})" if x.get("pctile") is not None else ""
        rows.append([f"**{x['k']}배**", f"{x['vs_rev0']:.1f}배", f"{_pct(x['dcf_cagr'])} {tail}".strip(), _pct(x["prob"], 0), txt[str(x["k"])].get("verdict", "")])
    note = "지금 매출 = 기준연도 매출 " + _money(c["rev0"], unit) + ". 5년 뒤 확률 = 몬테카를로에서 5년 뒤 주주가치가 지금 시가총액의 k배 이상인 비율(할인 전). 기저율 = 같은 매출 규모 미국 상장사가 실제로 달성한 5년 CAGR 분포."
    if mkt.get("size"):
        rows = [row[:2] + [f"{x['share'] * 100:.1f}%"] + row[2:] for row, x in zip(rows, c["rows"])]
        head = head[:2] + [f"{mkt.get('name', '참조 시장')} 점유"] + head[2:]
        note += f" 점유 기준 {mkt.get('name', '참조 시장')} {_money(mkt['size'], unit)}" + (f" — {mkt['basis']}" if mkt.get("basis") else "")
    B.append({"type": "table", "title": "배수 단계별 달성 가능성", "headers": head, "rows": rows, "note": note})
    bars = [{"label": a["label"], "bars": [{"name": "회사 경로·추정", "color": "c", "value": a["value"]}]} for a in lad.get("refs") or []]
    bars += [{"label": f"{x['k']}배에 필요한 매출", "bars": [{"name": "필요 매출", "color": "b", "value": round(x["rev"], 2)}]} for x in c["rows"]]
    if bars:
        B.append({"type": "chart", "chart": {"kind": "hbars", "pin": 9, "w": 480, "label_w": 150, "title": f"배수 단계별 필요 매출 vs 회사 경로 ({unit})", "unit": f" {unit}", "rows": bars}})
    for x in c["rows"]:
        s = txt[str(x["k"])]
        B.append({"type": "h3", "text": f"{x['k']}배 — {_money(x['target'], unit)}" + (f" · {s['verdict']}" if s.get("verdict") else "")})
        B.append({"type": "ul", "items": [f"**필요 조건:** {_need_line(x, unit)}", f"**어떻게 성장해야 하나:** {s['path']}", f"**펀더멘털 전망:** {s['outlook']}"]})
    return {"h2": f"배수 사다리 — {label(c['steps'])}가 되려면", "blocks": B}


def summary_item(dp, co, r, strict=True):
    lad = (dp or {}).get("ladder") or {}
    c = compute(dp, co, r, strict)
    unit = c["unit"]
    parts = []
    for x in c["rows"]:
        v = (lad.get("steps") or {}).get(str(x["k"]), {}).get("verdict", "")
        parts.append(f"**{x['k']}배** 시가총액 {_money(x['target'], unit)} = {_need_line(x, unit)}, 5년 뒤 확률 {_pct(x['prob'], 0)}" + (f", {v}" if v else ""))
    return {"q": f"{label(c['steps'])}가 되려면?", "a": " · ".join(parts) + (f". {lad['summary']}" if lad.get("summary") else ""), "auto": True}
