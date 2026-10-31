"""v2 밸류에이션 결과 → 텐배거 리포트 '밸류에이션' 절 블록 (2026-10-29 마스터 지시 — 맥킨지·IB 방식이 리포트에 실제로 들어가게)

scripts/valuation/v2/run.py의 evaluate()를 다시 돌려(같은 시드) 다음을 report_html.py 블록으로 만든다:
  ① 할인율(WACC) 구성표 — 바텀업 베타·ERP·국가위험(McKinsey·Damodaran)
  ② 시나리오 표 — 확률·지금 가치/시총·5년 뒤·5년 매출 CAGR, 기본 시나리오 ROIC·계속가치 비중·경제적 이익 항등 오차
  ③ 몬테카를로 분포(histogram) — 지금 가치/시총, P10·P50·P90·기대값
  ④ 가격 내포 기대 vs 기저율(hbars) — 시장 내포 CAGR·기본·2배·10배 필요 CAGR과 그 기저율 백분위(Mauboussin)
  ⑥ 멀티플 — scripts/valuation/v2/multiples.py(과거·동종 레인지, 펀더멘털 내재, 할인 분해, 합리적 멀티플, ROIC 비례 표)
  ⑤ 민감도 격자 — 장기 이익률 × 매출÷투하자본(기본 시나리오 가치/시총). 2026-10-29 CBRS 점검: 계속가치가 RONIC = WACC라
     영구성장률은 가치를 거의 바꾸지 않는다 → 가치를 실제로 가르는 두 동인으로 바꾸고, WACC·RONIC 민감도는 한 줄로
  ⑥ 상대가치(comps) — 동종사 EV/매출 vs 성장 회귀(데이터 묶음 peers가 있을 때), 내포 배수와 현재 배수
  ⑦ 동인 출처(provenance) — 컨센서스·가이던스·어닝콜·재무 중 어디서 왔는지
  ⑧ 별도 절 '어닝콜 변화·컨센서스·멀티플 프리미엄·EPS 리비전' — scripts/tenbagger/earnings_view.py(직전 콜 대비 변화의 가치 영향, 실적 vs 컨센서스,
     같은 분기 리비전과 주가 분해, 동종 대비 멀티플 프리미엄). 밸류에이션 절 바로 앞에 넣는다
  ⑨ 별도 절 세 개(2026-10-29 마스터 지시, 재료가 있을 때만): '내러티브'(narrative_view.py — datapack narrative + 멀티플 엔진 회사 고유 프리미엄 +
     EPS 리비전), '수급 — 누가 왜 샀나'(flow.py — ohlcv.csv + FINRA 공개 API), '가격 구간 — 월·주·일 피보나치'(levels.py — ohlcv.csv + raw.anchors).
     순서: 어닝콜 → 내러티브 근거 → 밸류에이션 → 수급 → 가격 구간 → (모델의 시나리오 절)
  ⑩ 맨 앞 절 두 개(마스터 지시 2026-10-30): ① 내러티브(narrative_view.lead_section) ② 배수 사다리(ladder.py) — 한 장 요약 맨 앞에도 같은 순서로 넣고, 모델이 쓴 번호를 다시 매긴다
사용: py scripts/tenbagger/v2_to_report.py <entity_id> --merge outputs/tenbagger/reports/<날짜>_<티커>.json
      (merge 없이 --out <파일>이면 절만 따로 저장)
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "scripts" / "valuation" / "v2"
sys.path.insert(0, str(V2))
import dcf  # noqa: E402
import ladder  # noqa: E402
import montecarlo  # noqa: E402
import run as v2run  # noqa: E402
import scenarios  # noqa: E402


def histogram(xs, bins=14, lo=None, hi=None):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return [], []
    lo = xs[int(len(xs) * 0.01)] if lo is None else lo
    hi = xs[int(len(xs) * 0.99) - 1] if hi is None else hi
    w = (hi - lo) / bins or 1
    counts = [0] * bins
    for x in xs:
        i = min(bins - 1, max(0, int((x - lo) / w)))
        counts[i] += 1
    labels = [f"{lo + w * (i + 0.5):.2f}" for i in range(bins)]
    return labels, [round(c / len(xs) * 100, 1) for c in counts]


def comps(peers, target_growth, target_ev_sales):
    """EV/매출 = a + b × 성장 (최소제곱). 동종 4개 미만이면 중앙값. 동종 값은 ev_sales·growth(기준은 datapack peers_basis) —
    예전 이름 ev_sales_ntm·growth_ntm도 읽는다"""
    pts = [(p.get("growth", p.get("growth_ntm")), p.get("ev_sales", p.get("ev_sales_ntm"))) for p in peers or []]
    pts = [(g, v) for g, v in pts if g is not None and v]
    if not pts:
        return None
    if len(pts) < 4:
        med = sorted(v for _, v in pts)[len(pts) // 2]
        return {"method": f"동종 {len(pts)}사 중앙값", "implied": med, "current": target_ev_sales, "r2": None}
    n = len(pts)
    mx, my = sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts) or 1e-9
    b = sum((x - mx) * (y - my) for x, y in pts) / sxx
    a = my - b * mx
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in pts)
    ss_tot = sum((y - my) ** 2 for _, y in pts) or 1e-9
    return {"method": f"동종 {n}사 회귀 EV/매출 = {a:.2f} + {b:.1f}×성장", "implied": a + b * target_growth, "current": target_ev_sales,
            "r2": 1 - ss_res / ss_tot, "points": pts}


def build(entity, draws=3000):
    r = v2run.evaluate(entity, draws=draws)
    co = v2run.load_company(entity)
    co["market"] = v2run.resolve_market(co)
    mcap, c, b, u = r["mcap"], r["coc"], r["base"], r["upside"]
    base_d = scenarios.drivers(co, co["scenarios"]["base"], c["wacc"], r["g_term"])
    blocks = [{"type": "p", "text": f"**방법:** 맥킨지식 재무 재구성(NOPAT·투하자본·ROIC) → 바텀업 WACC → FCFF DCF + 가치 동인 계속가치(ROIC·성장) → 경제적 이익 항등 검증 → 시나리오·몬테카를로 → 가격 내포 기대(역DCF)와 매출 성장 기저율. 단위 {r['unit']}, 모든 가치는 **현재 시가총액 대비 배수**로 표기(목표주가 아님)."}]
    blocks.append({"type": "table", "title": "할인율(WACC) 구성", "headers": ["항목", "값"], "rows": [
        ["무위험(미 10년)", f"{c['rf']:.2%}"], ["주식 위험 프리미엄", f"{c['erp']:.2%}"], ["레버드 베타(바텀업)", f"{c['beta']:.2f} (무레버 {c['beta_unlevered']:.2f})"],
        ["국가위험", f"{c['crp']:.2%}"], ["자기자본비용", f"{c['ke']:.2%}"], ["부채비중", f"{c['debt_weight']:.0%}"], ["WACC", f"**{c['wacc']:.2%}**"], ["영구성장", f"{r['g_term']:.1%}"]]})
    ko = {"base": "기본", "bull": "강세", "bear": "약세"}
    rows = []
    for n, s in r["scenarios"].items():
        sd = scenarios.drivers(co, co["scenarios"][n], c["wacc"], r["g_term"])
        rows.append([ko.get(n, n), f"{s['prob']:.0%}", f"{s['v0'] * mcap:,.1f}", f"**{s['v0']:.2f}배**", f"{s['v5']:.2f}배", f"{s['cagr5']:.1%}", f"{sd['margin'][4]:.0%}"])
    blocks.append({"type": "table", "title": f"시나리오별 DCF 주주가치 ÷ 현재 시가총액({mcap:,.1f} {r['unit']})",
                   "headers": ["시나리오", "확률", f"주주가치({r['unit']})", "지금", "5년 뒤(할인 전)", "5년 매출 CAGR", "5년차 영업이익률"], "rows": rows})
    blocks.append({"type": "p", "text": "**읽는 법:** '배'는 PER·EV/매출 같은 멀티플이 아니라 **DCF로 계산한 주주가치 ÷ 지금 시가총액**이다. 1.0배 = 그 시나리오 가정이 지금 주가와 같은 가치, 0.3배 = 가정대로면 주가의 30%만 현금흐름으로 설명된다. "
                   "'5년 뒤'는 5년 뒤 시점의 주주가치(그때 돈, 할인 전)를 지금 시가총액으로 나눈 값 — 지금 사서 5년 들고 있을 때 그 시점 내재가치가 지금 가격의 몇 배인가. 매년 약 WACC만큼 커진다(배당 없음, 적자 현금흐름은 차입으로 메운다고 가정)."})
    ev_b = dcf.value(base_d)["ev"]
    pv_cv = ev_b * b["cv_share"]
    blocks.append({"type": "p", "text": f"기본 시나리오 분해: 기업가치 {ev_b:,.1f} = 1~10년 현금흐름 현재가치 {ev_b - pv_cv:,.1f} + 11년차 이후(계속가치) {pv_cv:,.1f} {r['unit']}"
                   f"(초기 재투자가 커서 1~10년 합이 음수면 계속가치가 기업가치의 100%를 넘는다) · 순현금 {-base_d['net_debt']:,.1f} · ROIC 1년차 {b['roic_y1']:.0%} → 5년차 {b['roic_y5']:.0%} · "
                   f"경제적 이익 항등 오차 {b['ep_gap']:.1e}(DCF와 EP 가치가 같아야 정상) · 할인율 +50bp → 가치 {r['rate_50bp']['chg']:+.1%}"})
    mc = montecarlo.simulate(co, c["wacc"], r["g_term"], 5, draws, 20261028)
    labels, pct = histogram([v / mcap for v in mc["v0"]])
    if labels:
        blocks.append({"type": "chart", "chart": {"kind": "bars", "title": f"몬테카를로 {mc['used']:,}회 — 지금 가치/시가총액 분포 (%)", "unit": "%", "categories": labels,
                       "series": [{"name": "빈도", "color": "c", "values": pct}],
                       "conclusion": ladder.mc_reading(mc["used"], sum(1 for v in mc["v0"] if v >= mcap) / len(mc["v0"]), u["v0_p10"], u["v0_p50"], u["v0_p90"], u["p_h"],
                                                       ladder.steps_for(mcap * float(co.get("unit_usd", 1e9)))),
                       "note": f"P10 {u['v0_p10']:.2f} · P50 {u['v0_p50']:.2f} · P90 {u['v0_p90']:.2f} · 기대 {u['v0_mean']:.2f}배 · 30% 이상 고평가 확률 {u['p_over_30pct_overvalued']:.0%} · 5년 뒤 " + " · ".join(f"≥{k:g}배 {p:.0%}" for k, p in u['p_h'].items())}})
    bars = []
    if u.get("implied_cagr") is not None:
        bars.append({"label": "시장 내포", "bars": [{"name": "5년 매출 CAGR %", "color": "e", "value": round(u["implied_cagr"] * 100, 1)}]})
    bars.append({"label": "우리 기본", "bars": [{"name": "5년 매출 CAGR %", "color": "c", "value": round(u["base_cagr"] * 100, 1)}]})
    steps = ladder.steps_for(mcap * float(co.get("unit_usd", 1e9)))   # 시가총액 구간의 배수만(마스터 지시 2026-10-30)
    for mult, (rc, _) in u["required"].items():
        if rc is not None and mult in steps:
            bars.append({"label": f"{mult}배 필요", "bars": [{"name": "5년 매출 CAGR %", "color": "b", "value": round(rc * 100, 1)}]})
    pct_note = []
    for name, t in (("시장 내포", u.get("implied_pct")), ("기본", u.get("base_pct"))):
        if t and t[0] is not None:
            pct_note.append(f"{name} 기저율 상위 {100 - t[0]:.0f}%(n={t[1]}, {t[2]})")
    for mult, (rc, t) in u["required"].items():
        if t and t[0] is not None and mult in steps:
            pct_note.append(f"{mult}배 필요 성장 기저율 상위 {100 - t[0]:.0f}%")
    # pin 3 = 갤러리 3번째(마스터 지시 2026-10-30 "그림 11을 그림 2~4 사이로 올려라")
    blocks.append({"type": "chart", "chart": {"kind": "hbars", "pin": 3, "title": "가격 내포 기대 vs 필요 성장 (5년 매출 CAGR %)", "unit": "%", "rows": bars,
                   "note": " · ".join(pct_note) + " — 기저율: 같은 매출 규모 미국 상장사가 실제로 달성한 5년 CAGR 분포(SEC 재무)"}})
    bs = co["scenarios"]["base"]
    s2cs = sorted({round(bs.get("s2c") or 1.0, 2), 0.75, 1.5, 2.5})
    lrs = sorted({round(bs["margin"]["target"], 2), 0.15, 0.30, 0.40}) if isinstance(bs["margin"], dict) else [0.15, 0.30, 0.40]
    grid_rows = []
    for lr in lrs:
        row = [f"장기 이익률 {lr:.0%}"]
        for s2 in s2cs:
            sc = {**bs, "margin": {**bs["margin"], "target": lr, "lr": lr}, "s2c": s2}
            try:
                row.append(f"{dcf.value(scenarios.drivers(co, sc, c['wacc'], r['g_term']))['equity'] / mcap:.2f}")
            except (ValueError, ZeroDivisionError, TypeError):
                row.append("-")
        grid_rows.append(row)
    blocks.append({"type": "table", "title": "민감도 — 기본 시나리오 가치/시총(매출 경로 고정, 장기 이익률 × 매출÷투하자본)",
                   "headers": [""] + [f"매출÷투하자본 {s:g}" for s in s2cs], "rows": grid_rows})
    alt = []
    for label, d in (("WACC −1%p", dict(base_d, wacc=c["wacc"] - 0.01)), ("WACC +1%p", dict(base_d, wacc=c["wacc"] + 0.01)),
                     ("RONIC 20%(11년차 이후 성장이 가치 창출)", dict(base_d, ronic=0.20))):
        try:
            alt.append(f"{label} {dcf.value(d)['equity'] / mcap:.2f}배")
        except (ValueError, ZeroDivisionError):
            pass
    blocks.append({"type": "p", "text": "매출÷투하자본 = 매출 1달러를 늘리는 데 드는 설비·운전자본(높을수록 가볍다). 장기 이익률은 4년차 목표와 이후 수렴값을 같이 바꾼 것. "
                   f"계속가치는 RONIC = WACC(11년차 이후 성장은 가치를 만들지 않는다는 맥킨지 보수 가정) · 다른 축: " + " · ".join(alt)})
    dp_path = ROOT / "knowledge" / "models" / "companies" / entity / "datapack.json"
    if dp_path.exists():
        dp = json.loads(dp_path.read_text(encoding="utf-8"))
        # 멀티플(2026-10-29 마스터 지시): 과거 레인지 → 동종 레인지 → ROIC·성장·이익률 기반 펀더멘털 내재 → 할인·프리미엄 분해 → 합리적 멀티플
        import multiples
        mm = multiples.analyze(dp, base_d, mcap, c["wacc"], r["g_term"])
        r["_mm"] = mm   # 내러티브 절이 회사 고유 프리미엄을 쓴다
        if mm.get("current") and mm["peers"]:
            blocks.extend(multiples.report_blocks(mm, r["unit"], mcap, co.get("name", entity)))
        import datapack_check
        chk = datapack_check.check(dp)
        blocks.append({"type": "table", "title": f"데이터 검증 — 원자료 ↔ 밸류에이션 입력 대조 {chk['score']}/10",
                       "headers": ["검사", "결과", "내용"], "rows": [[c["name"], c["status"], c["detail"][:140]] for c in chk["checks"]]})
    blocks.append({"type": "hl", "text": "의사결정 보조(투자자문 아님): " + " / ".join(v2run.decision.lines(r["decision"])) if r.get("decision") else "의사결정 보조 지표 미산출"})
    return {"h2": "밸류에이션 — 맥킨지·IB 방식(v2 엔진)", "blocks": blocks}, r


def earnings_section(entity, r):
    """⑧ 어닝콜 변화의 가치 영향·실적 vs 컨센서스·EPS 리비전·멀티플 프리미엄(2026-10-29 마스터 지시) — scripts/tenbagger/earnings_view.py"""
    dp_path = ROOT / "knowledge" / "models" / "companies" / entity / "datapack.json"
    if not dp_path.exists():
        return None
    import earnings_view
    co = v2run.load_company(entity)
    co["market"] = v2run.resolve_market(co)
    return earnings_view.report_section(json.loads(dp_path.read_text(encoding="utf-8")), co, r["mcap"], r["coc"]["wacc"], r["g_term"], r["unit"])


def extra_sections(entity, r, strict=True):
    """⑨ 내러티브·수급·가격 구간 — 재료가 없으면 None(그 절만 빠진다)"""
    dp_path = ROOT / "knowledge" / "models" / "companies" / entity / "datapack.json"
    dp = json.loads(dp_path.read_text(encoding="utf-8")) if dp_path.exists() else {}
    import flow
    import levels
    import narrative_view
    co = v2run.load_company(entity)
    co["market"] = v2run.resolve_market(co)
    out = {"lead": narrative_view.lead_section(dp, r.get("_mm")), "ladder": ladder.report_section(dp, co, r, strict),
           "narrative": narrative_view.report_section(dp, r.get("_mm")), "flow": None, "levels": None, "summary": []}
    if out["lead"]:
        out["summary"].append(narrative_view.summary_item(dp))
    if out["ladder"]:
        out["summary"].append(ladder.summary_item(dp, co, r, strict))
    for k, mod in (("flow", flow), ("levels", levels)):
        try:
            sec = mod.report_section(entity, dp)
        except Exception as exc:   # 외부 조회(FINRA) 실패가 리포트 전체를 막지 않게
            print(f"  [{k}] 절 생략: {type(exc).__name__}: {exc}")
            sec = None
        if sec:
            sec.pop("_summary", None)
        out[k] = sec
    return out


EXTRA_H2 = ("내러티브 — ", "내러티브 근거 — ", "수급 — ", "가격 구간 — ", "배수 사다리 — ")
CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _strip_no(s):
    return str(s or "").lstrip(CIRCLED + " ")


def renumber(items, key):
    """맨 앞 자동 절·요약 다음으로 모델이 쓴 번호를 다시 매긴다 — 번호 없는 자동 절은 그대로"""
    n = 0
    for it in items:
        lead = it.get("auto") or it.get(key, "").startswith(("내러티브 — ", "배수 사다리 — "))
        if lead or str(it.get(key) or "")[:1] in CIRCLED:
            it[key] = f"{CIRCLED[n]} {_strip_no(it[key])}"
            n += 1


def merge_lead(d, lead, lad, summary):
    """내러티브 → 배수 사다리를 본문·요약 맨 앞에(마스터 지시 2026-10-30 "요약 처음과 세부 설명 처음에 … 내러티브를 먼저")"""
    d["sections"] = [x for x in (lead, lad) if x] + d["sections"]
    d["summary"] = summary + [s for s in d.get("summary") or [] if not s.get("auto")]
    renumber(d["sections"], "h2")
    renumber(d["summary"], "q")
    return d


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("entity")
    ap.add_argument("--merge")
    ap.add_argument("--out")
    ap.add_argument("--draws", type=int, default=3000)
    ap.add_argument("--legacy", action="store_true", help="datapack에 narrative.lead·ladder가 없는 옛 리포트 정정용")
    a = ap.parse_args(argv)
    sec, r = build(a.entity, a.draws)
    esec = earnings_section(a.entity, r)
    xs = extra_sections(a.entity, r, strict=not a.legacy)
    if a.merge:
        fw = json.loads((ROOT / "knowledge" / "models" / "companies" / a.entity / "datapack.json").read_text(encoding="utf-8")).get("forward") or {}
        if not a.legacy and "horizons" not in fw:
            raise SystemExit("datapack에 Fwd 1Y·2Y·3Y 멀티플이 없다 — scripts/fiscal/templates/forward_multiples.js → adapter --forward-multiples 먼저(docs/tasks/chiip-tenbagger-report.md 2번). 옛 리포트 정정은 --legacy")
        if not a.legacy and not (xs["lead"] and xs["ladder"]):
            raise SystemExit("datapack에 narrative.lead와 ladder가 있어야 한다(docs/tasks/chiip-tenbagger-report.md 2번) — 옛 리포트 정정은 --legacy")
        p = Path(a.merge)
        d = json.loads(p.read_text(encoding="utf-8"))
        d["sections"] = [s for s in d.get("sections") or [] if not _strip_no(s.get("h2")).startswith(("밸류에이션 — 맥킨지", "어닝콜 변화·컨센서스") + EXTRA_H2)]
        idx = next((i for i, s in enumerate(d["sections"]) if "시나리오" in s.get("h2", "")), len(d["sections"]))
        for x in (xs["levels"], xs["flow"], sec, xs["narrative"], esec):   # 앞에 끼워 넣으므로 역순: 어닝콜 → 내러티브 근거 → 밸류에이션 → 수급 → 가격 구간
            if x:
                d["sections"].insert(idx, x)
        merge_lead(d, xs["lead"], xs["ladder"], xs["summary"])
        v = d.setdefault("verdict", {})
        v.setdefault("alpha", None)
        import report_html
        p.write_text(json.dumps(report_html.clean_vendor(d), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[v2→리포트] {p} 에 '밸류에이션' 절 병합 (블록 {len(sec['blocks'])}개)" + (f" + '어닝콜·컨센서스·멀티플·리비전' 절(블록 {len(esec['blocks'])}개)" if esec else " — 어닝콜·컨센서스 절 재료 없음(datapack call.deltas·consensus.surprise·revisions·multiples_now)"))
        print("  추가 절: " + " · ".join(f"{k} {'있음' if v else '재료 없음'}" for k, v in xs.items() if k != "summary"))
    if a.out or not a.merge:
        out = Path(a.out or f"{a.entity}_v2_section.json")
        out.write_text(json.dumps(sec, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[v2→리포트] {out}")
    u = r["upside"]
    print(f"  WACC {r['coc']['wacc']:.2%} · 기본 {r['base']['v0']:.2f}배 · MC P50 {u.get('v0_p50') or 0:.2f}배 · 5년 " + " · ".join(f"≥{k:g}배 {p:.0%}" for k, p in (u.get('p_h') or {}).items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
