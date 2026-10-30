"""텐배거 리포트 '어닝콜 변화·컨센서스·멀티플 프리미엄·EPS 리비전' 절 (마스터 지시 2026-10-29 "최신 어닝콜 내용(직전 분기 콜 대비
업데이트되거나 새로 나온 내용 중심으로 기업가치에 어떤 영향을 미치는지 정량화)과 재무 지표(컨센서스와 비교), 멀티플 프리미엄 및
EPS 리비전 등을 텐배거 리포트에 넣어라")

v2_to_report가 밸류에이션 절 앞에 이 절을 넣는다. 재료는 데이터 묶음(datapack.json) — 숫자는 모델이 원자료에서 옮기고, 계산은 여기서만.
  ① 어닝콜 변화의 가치 영향 — call.deltas 각 항목을 v2 기본 시나리오 동인 하나의 이동(shift)으로 바꾸고, 그 변화가 없었을 때(동인을 되돌린
     DCF)와 비교해 '단독 Δ가치 %'를 계산한다. 확신도(확정 1.0·가이던스 0.8·경영진 목표 0.5·정황 0.3)를 곱해 합산. 동인끼리 상호작용이 있어
     단독 합은 동시 적용과 다르다 → 둘 다 싣는다(factor_impact.py의 회사 전용 모델과 같은 방식을 v2 엔진에 일반화).
  ② 실적 vs 컨센서스 — consensus.surprise(분기·지표별 실적·추정) → 서프라이즈 %
  ③ EPS·매출 리비전 — consensus.revisions(직전 콜 시점 vs 지금, 같은 분기끼리) → 분기별·합계 리비전 %, 같은 기간 주가 변화를
     'EPS 리비전 × 멀티플 변화'로 분해(주가 = 이익 × 배수 → (1+주가) = (1+EPS 리비전)(1+리레이팅))
  ③-2 지난 12개월 EPS 리비전 추이·최근 4개 분기 주가 분해 — scripts/tenbagger/revision_view.py(재료 있으면 ③의 단일 구간 분해 그림을 대신한다, 2026-10-30)
  ④ 멀티플 프리미엄 — multiples_now(선행 P/E·EV/EBITDA·EV/매출·성장) vs peers 같은 지표의 중앙값 → 프리미엄 %, 성장 조정(배수 ÷ 성장%) 프리미엄

datapack 추가 필드:
  "call": {..., "prev_date": "2026-07-28",
           "deltas": [{"id","kind":"신규|업데이트|부정|반복","item","prior","latest","driver","shift","confidence","source"}]}
     driver = rev0 | growth_start | growth_end | growth_decay | margin_m0 | margin_target | margin_lr | s2c | wacc | net_debt   (shift는 직전 → 최신 변화량, 소수)
     growth_decay = 성장 감속 계수(gₜ = end + (start − end)·decay^(t−1)) — 수주잔고·슬롯처럼 '고성장이 얼마나 오래 가나'를 바꾸는 사실
  "consensus": {..., "surprise": [{"period":"2026Q3","metric":"매출","unit":"M$","actual":1167.9,"est":1045.7,"est_src":"zacks","basis":"gaap"}],
     ← Fiscal.ai 본보기 scripts/fiscal/templates/surprise.js 출력 rows 그대로(최근 4개 분기, EPS·조정 EBIT/EBITDA는 Non-GAAP, 2026-10-30)
  call.deltas 각 항목에 "label"(그래프에 쓸 짧은 이름, 16자 이내 — 예 "OpenAI 2GW 옵션")을 넣으면 그래프가 그 이름을 쓴다
                "revisions": {"from_date","to_date","from_label","source","rows":[{"period":"2026Q4","metric":"EPS","from":0.18,"to":0.1768}]},
                "price_window": {"from": 26.22, "to": 18.35}}
  "multiples_now": {"pe_fwd","ev_ebitda","ev_sales","growth"},  peers 각 행에 같은 이름(pe_fwd·ev_ebitda·ev_sales·growth)
사용: v2_to_report.py가 자동으로 부른다. 단독: py scripts/tenbagger/earnings_view.py <entity_id>
"""
import copy
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "scripts" / "valuation" / "v2"
sys.path.insert(0, str(V2))
import dcf  # noqa: E402
import scenarios  # noqa: E402

DRIVERS = {"rev0": "기준연도 매출", "growth_start": "1년차 성장률", "growth_end": "장기 성장 수렴값", "growth_decay": "성장 지속(감속 계수)", "margin_m0": "출발 이익률",
           "margin_target": "목표 이익률", "margin_lr": "장기 이익률", "s2c": "매출÷투하자본", "wacc": "할인율(WACC)", "net_debt": "순차입"}


def _apply(co, spec, wacc, driver, x):
    """기본 시나리오 사양에 동인 이동 x를 더한 (co, spec, wacc) 사본"""
    co, spec = copy.deepcopy(co), copy.deepcopy(spec)
    if driver == "rev0":
        co["rev0"] += x
    elif driver in ("growth_start", "growth_end", "growth_decay"):
        if isinstance(spec["growth"], list):
            spec["growth"] = [g + x for g in spec["growth"]] if driver == "growth_start" else spec["growth"]
        else:
            key = driver.split("_")[1]
            spec["growth"][key] = min(0.95, spec["growth"].get(key, 0.7) + x) if key == "decay" else spec["growth"][key] + x
    elif driver in ("margin_m0", "margin_target", "margin_lr"):
        if isinstance(spec["margin"], list):
            spec["margin"] = [m + x for m in spec["margin"]]
        else:
            key = driver.split("_")[1]
            if key == "m0" and spec["margin"].get("anchors"):   # 앵커(컨센서스 이익률)가 있으면 출발점 = 첫 앵커
                spec["margin"]["anchors"] = [spec["margin"]["anchors"][0] + x] + spec["margin"]["anchors"][1:]
            else:
                spec["margin"][key] = spec["margin"].get(key, spec["margin"]["target"] if key == "lr" else 0) + x
    elif driver == "s2c":
        spec["s2c"] = (spec.get("s2c") or co.get("s2c")) + x
    elif driver == "wacc":
        wacc += x
    elif driver == "net_debt":
        co["market"] = {**co["market"], "net_debt": co["market"]["net_debt"] + x}
    else:
        raise ValueError(f"모르는 동인: {driver}")
    return co, spec, wacc


def _equity(co, spec, wacc, g_term):
    return dcf.value(scenarios.drivers(co, spec, wacc, g_term))["equity"]


def call_value_impact(co, wacc, g_term, deltas):
    """직전 콜 → 최신 콜 변화 항목별 가치 영향. 기준 = 지금 동인(최신 정보 반영). 변화가 없었다면 = 그 동인을 shift만큼 되돌린 값.
    단독 Δ% = 기준 ÷ 되돌린 값 − 1. 동시 Δ% = 기준 ÷ 모든 항목을 함께 되돌린 값 − 1"""
    spec = co["scenarios"]["base"]
    base = _equity(co, spec, wacc, g_term)
    rows, all_co, all_spec, all_w = [], co, spec, wacc
    for d in deltas or []:
        if d.get("driver") not in DRIVERS or not d.get("shift"):
            rows.append({**d, "solo": 0.0, "weighted": 0.0})
            continue
        c2, s2, w2 = _apply(co, spec, wacc, d["driver"], -d["shift"])
        prior = _equity(c2, s2, w2, g_term)
        solo = base / prior - 1 if prior > 0 else None
        conf = d.get("confidence", 0.5)
        rows.append({**d, "solo": solo, "weighted": (solo or 0) * conf})
        all_co, all_spec, all_w = _apply(all_co, all_spec, all_w, d["driver"], -d["shift"])
    prior_all = _equity(all_co, all_spec, all_w, g_term)
    joint = base / prior_all - 1 if prior_all > 0 else None
    return {"rows": rows, "base_equity": base, "prior_equity": prior_all, "joint": joint,
            "solo_sum": sum(r["solo"] or 0 for r in rows), "weighted_sum": sum(r["weighted"] for r in rows)}


def surprises(rows, n=4):
    """최근 n개 분기만(마스터 지시 2026-10-30 "분기별 서프라이즈는 최근 4개 분기로 시계열") — 분기 오름차순"""
    out = []
    for r in rows or []:
        a, e = r.get("actual"), r.get("est")
        out.append({**r, "surprise": (a / e - 1) if a is not None and e else None})
    keep = sorted({str(r.get("period") or "") for r in out})[-n:]
    return sorted([r for r in out if str(r.get("period") or "") in keep], key=lambda r: (str(r.get("period") or ""), r.get("metric", "")))


def margin_surprises(sp):
    """이익률 서프라이즈(%p) — EBIT → OPM, 회사가 EBITA를 주요 지표로 쓰면 EBITA Margin(마스터 지시 2026-10-30). 추정은 같은 제공처 쌍(매출·이익)으로"""
    name, num = ("EBITA Margin", "EBITA") if any(r["metric"] == "EBITA" for r in sp) else ("OPM", "EBIT")
    rev = {r["period"]: r for r in sp if r["metric"] == "매출"}
    fam = lambda r: str(r.get("est_src") or "").split(":")[0]
    out = []
    for r in sp:
        v = rev.get(r["period"])
        if r["metric"] != num or not v or not v.get("actual"):
            continue
        act = r["actual"] / v["actual"] * 100
        est = r["est"] / v["est"] * 100 if r.get("est") and v.get("est") and fam(r) == fam(v) else None
        out.append({"period": r["period"], "metric": name, "actual": act, "est": est, "surprise": act - est if est is not None else None})
    return name, out


def short_label(r, n=16):
    """콜 변화 항목의 그래프 이름 — datapack의 label(짧은 이름)이 있으면 그것, 없으면 항목 내용 앞부분(F1·F2 같은 번호 대신, 2026-10-30)"""
    t = str(r.get("label") or r.get("item") or r.get("id") or "").strip()
    return t if len(t) <= n else t[:n - 1].rstrip() + "…"


def revisions(rv, price=None):
    """같은 분기·지표끼리 직전 시점 → 지금 리비전. 지표별 합계(같은 분기 집합)와 주가 분해"""
    rows = []
    for r in (rv or {}).get("rows") or []:
        f, t_ = r.get("from"), r.get("to")
        rows.append({**r, "rev": (t_ / f - 1) if f and t_ is not None else None})
    total = {}
    for m in sorted({r["metric"] for r in rows}):
        sel = [r for r in rows if r["metric"] == m and r.get("from") and r.get("to") is not None]
        if sel:
            f, t_ = sum(r["from"] for r in sel), sum(r["to"] for r in sel)
            total[m] = {"periods": [r["period"] for r in sel], "from": f, "to": t_, "rev": t_ / f - 1}
    decomp = None
    eps = total.get("EPS")
    if price and price.get("from") and price.get("to") and eps:
        p = price["to"] / price["from"] - 1
        rerate = (1 + p) / (1 + eps["rev"]) - 1
        decomp = {"price": p, "eps": eps["rev"], "rerate": rerate}
    return {"rows": rows, "total": total, "decomp": decomp}


def premiums(now, peers):
    """대상 배수 ÷ 동종 중앙값 − 1. 성장 조정 = (배수 ÷ 성장%) 끼리 비교 — 성장이 0 이하인 동종은 제외"""
    out = []
    for k, label in (("pe_fwd", "선행 P/E"), ("ev_ebitda", "EV/EBITDA"), ("ev_sales", "EV/매출")):
        v = (now or {}).get(k)
        pv = [p[k] for p in peers or [] if p.get(k) and p[k] > 0]
        if not v or len(pv) < 2:
            continue
        med = statistics.median(pv)
        g = (now or {}).get("growth")
        adj = [p[k] / (p["growth"] * 100) for p in peers if p.get(k) and p[k] > 0 and (p.get("growth") or 0) > 0]
        ga = (v / (g * 100) / statistics.median(adj) - 1) if g and g > 0 and len(adj) >= 2 else None
        out.append({"metric": label, "value": v, "peer_median": med, "n": len(pv), "premium": v / med - 1,
                    "growth_adj_premium": ga, "lo": min(pv), "hi": max(pv)})
    return out


def _pct(x, nd=1):
    return "-" if x is None else f"{x:+.{nd}%}"


def report_section(dp, co, mcap, wacc, g_term, unit="B$"):
    """report_html 절 하나. 재료가 하나도 없으면 None"""
    call, cons = dp.get("call") or {}, dp.get("consensus") or {}
    B = []
    deltas = call.get("deltas") or []
    if deltas:
        imp = call_value_impact(co, wacc, g_term, deltas)
        B.append({"type": "p", "text": f"**방법:** 직전 콜({call.get('prev_date', '미기재')}) → 최신 콜({call.get('date', '미기재')})에서 새로 나오거나 바뀐 항목을 v2 기본 시나리오의 동인 이동으로 옮기고, "
                  "그 변화가 없었을 때(동인을 되돌린 DCF) 대비 주주가치 변화를 잰다. 확신도: 확정 1.0 · 회사 가이던스 0.8 · 경영진 목표·장기 발언 0.5 · 정황 0.3. "
                  "'반복'은 직전 콜과 같은 말이라 가치 영향 0."})
        rows = []
        for r in imp["rows"]:
            drv = DRIVERS.get(r.get("driver"), "—")
            sh = r.get("shift")
            sh_txt = "—" if not sh else (f"{sh:+,.2f} {unit}" if r.get("driver") in ("rev0", "net_debt") else (f"{sh:+.2%}" if abs(sh) < 0.01 else f"{sh:+.1%}"))
            rows.append([r.get("kind", ""), r.get("item", ""), r.get("prior", ""), r.get("latest", ""),
                         f"{drv} {sh_txt}", f"{r.get('confidence', 0):.1f}", _pct(r["solo"])])
        rows.append(["**합계**", "단독 합", "", "", f"동시 적용 {_pct(imp['joint'])}", "", f"**{_pct(imp['solo_sum'])}**"])
        B.append({"type": "table", "title": "직전 콜 대비 새로 나오거나 바뀐 내용 → 가치 영향 (v2 기본 시나리오 주주가치 기준)",
                  "headers": ["항목", "내용", "직전 콜", "최신 콜", "모델 동인 이동", "확신도", "가치 영향"], "rows": rows})
        bars = [r for r in imp["rows"] if r["solo"]]
        if bars:
            # 가로 막대 + 항목 이름(마스터 지시 2026-10-30 "x축 F1~F9로는 직관적으로 파악하지 못한다") — 영향이 큰 순
            bars = sorted(bars, key=lambda r: -abs(r["solo"] or 0))   # 확신도 가중 수치는 싣지 않는다(마스터 지시 2026-10-30)
            B.append({"type": "chart", "chart": {"kind": "hbars", "w": 480, "label_w": 150, "title": "콜 변화 항목별 주주가치 영향 (%)", "unit": "%",
                      "rows": [{"label": short_label(r), "bars": [{"name": "가치 영향", "color": "c", "value": round(r["solo"] * 100, 1)}]} for r in bars],
                      "note": f"직전 콜 정보만으로 본 가치 {imp['prior_equity']:,.2f} → 최신 {imp['base_equity']:,.2f} {unit}(시가총액 {mcap:,.2f}의 {imp['prior_equity'] / mcap:.2f}배 → {imp['base_equity'] / mcap:.2f}배)"}})
    sp = surprises(cons.get("surprise"))
    if sp:
        sp = [r for r in sp if r["metric"] == "매출" or r.get("basis") in (None, "adjusted")]   # 이익 지표는 조정 값만(2026-10-30)
        mg_name, mg = margin_surprises(sp)
        order = ("매출", mg_name, "EPS")
        shown = sorted([r for r in sp if r["metric"] in order] + mg, key=lambda r: (r["period"], order.index(r["metric"])))

        def cells(r):
            if r["metric"] == mg_name:
                return f"{r['actual']:.1f}%", f"{r['est']:.1f}%" if r.get("est") is not None else "-", f"{r['surprise']:+.1f}%p" if r.get("surprise") is not None else "-"
            amt = lambda v: f"${v:,.2f}" if r.get("unit") == "$" else f"{v:,.4g} {r.get('unit', '')}"
            return amt(r["actual"]), amt(r["est"]) if r.get("est") else "-", _pct(r["surprise"])
        B.append({"type": "table", "title": "실적 vs 컨센서스 — 최근 4개 분기 (이익 지표는 조정 기준, 발표 직전 추정)", "headers": ["분기", "지표", "실적", "컨센서스", "서프라이즈"],
                  "rows": [[r["period"], r["metric"], *cells(r)] for r in shown]})
        per = sorted({r["period"] for r in shown if r["surprise"] is not None})
        pick = lambda p, m: next((round(r["surprise"] * (1 if m == mg_name else 100), 1) for r in shown if r["period"] == p and r["metric"] == m and r["surprise"] is not None), None)
        series_sp = [{"name": m, "color": c, "values": [pick(p, m) for p in per]} for m, c in zip(order, "ced")]
        series_sp = [s for s in series_sp if any(v is not None for v in s["values"])]
        if per:
            B.append({"type": "chart", "chart": {"kind": "bars", "w": 440, "title": f"분기별 서프라이즈 — {'·'.join(s['name'] for s in series_sp)} (%, {mg_name}은 %p), 최근 4개 분기", "unit": "%",
                                                 "categories": per, "series": series_sp}})
    import revision_view
    series = revision_view.blocks(dp)   # 그림 5·8 — 지난 12개월 리비전 추이와 최근 4개 분기 분해(마스터 지시 2026-10-30)
    B.extend(series)
    rv = cons.get("revisions")
    if rv:
        res = revisions(rv, cons.get("price_window"))
        B.append({"type": "table", "title": f"컨센서스 리비전 — {rv.get('from_label', rv.get('from_date', '직전'))}({rv.get('from_date', '')}) → 지금({rv.get('to_date', '')}), 같은 분기끼리",
                  "headers": ["분기", "지표", "직전", "지금", "리비전"],
                  "rows": [[r["period"], r["metric"], f"{r['from']:,.4g}" if r.get("from") is not None else "-", f"{r['to']:,.4g}" if r.get("to") is not None else "-", _pct(r["rev"])] for r in res["rows"]]
                  + [[f"**합계 {len(v['periods'])}분기**", m, f"{v['from']:,.4g}", f"{v['to']:,.4g}", f"**{_pct(v['rev'])}**"] for m, v in res["total"].items()]})
        d = res["decomp"]
        if d and not series:   # 시계열 재료가 없는 옛 데이터 묶음만 단일 구간 분해
            B.append({"type": "chart", "chart": {"kind": "bars", "title": "같은 기간 주가 변화 분해 = EPS 리비전 × 멀티플 변화 (%)", "unit": "%", "categories": ["주가", "EPS 리비전", "멀티플(리레이팅)"],
                      "series": [{"name": "변화", "color": "c", "values": [round(d["price"] * 100, 1), round(d["eps"] * 100, 1), round(d["rerate"] * 100, 1)]}],
                      "note": "(1 + 주가 변화) = (1 + EPS 리비전) × (1 + 멀티플 변화). EPS 리비전은 위 표의 같은 분기 합 기준"}})
            who = "이익 추정 하향" if abs(d["eps"]) > abs(d["rerate"]) else "멀티플(시장이 붙이는 배수) 변화"
            B.append({"type": "p", "text": f"**해석:** 이 기간 주가 {_pct(d['price'])} 중 EPS 추정 변화가 {_pct(d['eps'])}, 멀티플 변화가 {_pct(d['rerate'])} — 주가를 움직인 것은 **{who}**이다. "
                      + ("이익 추정은 오르는데 주가가 내렸다면 시장은 숫자가 아니라 지속성·위험(할인율)을 다시 매긴 것이다." if d["eps"] > 0 > d["price"] else "")})
        if rv.get("source"):
            B.append({"type": "p", "text": f"리비전 출처: {rv['source']}"})
    pm = premiums(dp.get("multiples_now"), dp.get("peers"))
    if pm:
        B.append({"type": "table", "title": "멀티플 프리미엄 — 동종 중앙값 대비 (성장 조정 = 배수 ÷ 최근 분기 전년 대비 매출 성장%, 한 분기 성장이라 변동이 크다)",
                  "headers": ["지표", "대상", "동종 중앙값(범위)", "프리미엄", "성장 조정 프리미엄"],
                  "rows": [[r["metric"], f"{r['value']:.1f}배", f"{r['peer_median']:.1f}배 ({r['lo']:.1f}~{r['hi']:.1f}, {r['n']}사)", f"**{_pct(r['premium'], 0)}**", _pct(r["growth_adj_premium"], 0)] for r in pm]})
        B.append({"type": "chart", "chart": {"kind": "bars", "title": "멀티플 프리미엄 (%) — 0 = 동종 중앙값", "unit": "%", "categories": [r["metric"] for r in pm],
                  "series": [{"name": "단순", "color": "c", "values": [round(r["premium"] * 100) for r in pm]},
                             {"name": "성장 조정", "color": "d", "values": [round(r["growth_adj_premium"] * 100) if r["growth_adj_premium"] is not None else None for r in pm]}]}})
    if not B:
        return None
    return {"h2": "어닝콜 변화·컨센서스·멀티플 프리미엄·EPS 리비전", "blocks": B}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    import run as v2run
    eid = argv[0]
    dp = json.loads((ROOT / "knowledge" / "models" / "companies" / eid / "datapack.json").read_text(encoding="utf-8"))
    r = v2run.evaluate(eid, draws=200)
    co = v2run.load_company(eid)
    co["market"] = v2run.resolve_market(co)
    sec = report_section(dp, co, r["mcap"], r["coc"]["wacc"], r["g_term"], r["unit"])
    print(json.dumps(sec, ensure_ascii=False, indent=1) if sec else "재료 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
