"""v2 밸류에이션 결과 → 텐배거 리포트 '밸류에이션' 절 블록 (2026-10-29 마스터 지시 — 맥킨지·IB 방식이 리포트에 실제로 들어가게)

scripts/valuation/v2/run.py의 evaluate()를 다시 돌려(같은 시드) 다음을 report_html.py 블록으로 만든다:
  ① 할인율(WACC) 구성표 — 바텀업 베타·ERP·국가위험(McKinsey·Damodaran)
  ② 시나리오 표 — 확률·지금 가치/시총·5년 뒤·5년 매출 CAGR, 기본 시나리오 ROIC·계속가치 비중·경제적 이익 항등 오차
  ③ 몬테카를로 분포(histogram) — 지금 가치/시총, P10·P50·P90·기대값
  ④ 가격 내포 기대 vs 기저율(hbars) — 시장 내포 CAGR·기본·2배·10배 필요 CAGR과 그 기저율 백분위(Mauboussin)
  ⑤ 민감도 격자 — WACC ±1%p × 영구성장 ±0.5%p(기본 시나리오 가치/시총)
  ⑥ 상대가치(comps) — 동종사 EV/매출 vs 성장 회귀(데이터 묶음 peers가 있을 때), 내포 배수와 현재 배수
  ⑦ 동인 출처(provenance) — 컨센서스·가이던스·어닝콜·재무 중 어디서 왔는지
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
    """EV/매출 = a + b × 성장 (최소제곱). 동종 4개 미만이면 중앙값"""
    pts = [(p["growth_ntm"], p["ev_sales_ntm"]) for p in peers or [] if p.get("growth_ntm") is not None and p.get("ev_sales_ntm")]
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
    rows = [[n, f"{s['prob']:.0%}", f"{s['v0']:.2f}배", f"{s['v5']:.2f}배", f"{s['cagr5']:.1%}"] for n, s in r["scenarios"].items()]
    blocks.append({"type": "table", "title": "시나리오별 내재가치 (현재 시가총액 대비)", "headers": ["시나리오", "확률", "지금", "5년 뒤", "5년 매출 CAGR"], "rows": rows})
    blocks.append({"type": "p", "text": f"기본 시나리오: ROIC 1년차 {b['roic_y1']:.0%} → 5년차 {b['roic_y5']:.0%} · 계속가치 비중 {b['cv_share']:.0%} · 경제적 이익 항등 오차 {b['ep_gap']:.1e}(DCF와 EP 가치가 같아야 정상) · 할인율 +50bp → 가치 {r['rate_50bp']['chg']:+.1%}(듀레이션 약 {r['rate_50bp']['duration']:.0f}년)"})
    mc = montecarlo.simulate(co, c["wacc"], r["g_term"], 5, draws, 20261028)
    labels, pct = histogram([v / mcap for v in mc["v0"]])
    if labels:
        blocks.append({"type": "chart", "chart": {"kind": "bars", "title": f"몬테카를로 {mc['used']:,}회 — 지금 가치/시가총액 분포 (%)", "unit": "%", "categories": labels,
                       "series": [{"name": "빈도", "color": "c", "values": pct}],
                       "note": f"P10 {u['v0_p10']:.2f} · P50 {u['v0_p50']:.2f} · P90 {u['v0_p90']:.2f} · 기대 {u['v0_mean']:.2f}배 · 30% 이상 고평가 확률 {u['p_over_30pct_overvalued']:.0%} · 5년 뒤 " + " · ".join(f"≥{k:g}배 {p:.0%}" for k, p in u['p_h'].items())}})
    bars = []
    if u.get("implied_cagr") is not None:
        bars.append({"label": "시장 내포", "bars": [{"name": "5년 매출 CAGR %", "color": "e", "value": round(u["implied_cagr"] * 100, 1)}]})
    bars.append({"label": "우리 기본", "bars": [{"name": "5년 매출 CAGR %", "color": "c", "value": round(u["base_cagr"] * 100, 1)}]})
    for mult, (rc, _) in u["required"].items():
        if rc is not None:
            bars.append({"label": f"{mult}배 필요", "bars": [{"name": "5년 매출 CAGR %", "color": "b", "value": round(rc * 100, 1)}]})
    pct_note = []
    for name, t in (("시장 내포", u.get("implied_pct")), ("기본", u.get("base_pct"))):
        if t and t[0] is not None:
            pct_note.append(f"{name} 기저율 상위 {100 - t[0]:.0f}%(n={t[1]}, {t[2]})")
    for mult, (rc, t) in u["required"].items():
        if t and t[0] is not None:
            pct_note.append(f"{mult}배 필요 성장 기저율 상위 {100 - t[0]:.0f}%")
    blocks.append({"type": "chart", "chart": {"kind": "hbars", "title": "가격 내포 기대 vs 필요 성장 (5년 매출 CAGR %)", "unit": "%", "rows": bars,
                   "note": " · ".join(pct_note) + " — 기저율: 같은 매출 규모 미국 상장사가 실제로 달성한 5년 CAGR 분포(SEC 재무)"}})
    grid_rows = []
    for dw in (-0.01, -0.005, 0.0, 0.005, 0.01):
        row = [f"WACC {c['wacc'] + dw:.1%}"]
        for dg in (-0.005, 0.0, 0.005):
            d = dict(base_d, wacc=c["wacc"] + dw, g_term=r["g_term"] + dg)
            try:
                row.append(f"{dcf.value(d)['equity'] / mcap:.2f}")
            except (ValueError, ZeroDivisionError):
                row.append("-")
        grid_rows.append(row)
    blocks.append({"type": "table", "title": "민감도 — 기본 시나리오 가치/시총", "headers": ["", f"영구성장 {r['g_term'] - 0.005:.1%}", f"{r['g_term']:.1%}", f"{r['g_term'] + 0.005:.1%}"], "rows": grid_rows})
    dp_path = ROOT / "knowledge" / "models" / "companies" / entity / "datapack.json"
    if dp_path.exists():
        dp = json.loads(dp_path.read_text(encoding="utf-8"))
        revs = [dp["consensus"]["rev"][k] for k in sorted((dp.get("consensus") or {}).get("rev") or {})]
        g_ntm = revs[1] / revs[0] - 1 if len(revs) >= 2 else None
        ev = mcap + co["market"]["net_debt"]
        cur = ev / revs[1] if len(revs) >= 2 else None
        cp = comps(dp.get("peers"), g_ntm, cur) if g_ntm is not None else None
        if cp:
            blocks.append({"type": "chart", "chart": {"kind": "hbars", "title": f"상대가치 — EV/선행 매출 ({cp['method']})", "unit": "배", "rows": [
                {"label": "동종 내포", "bars": [{"name": "EV/매출", "color": "d", "value": round(cp["implied"], 2)}]},
                {"label": "현재", "bars": [{"name": "EV/매출", "color": "b", "value": round(cp["current"], 2)}]}],
                "note": (f"회귀 설명력 R² {cp['r2']:.2f}" if cp.get("r2") is not None else "동종 4사 미만 — 중앙값") + f" · 대상 선행 성장 {g_ntm:.1%}"}})
    prov = co.get("provenance") or {}
    if prov:
        blocks.append({"type": "table", "title": "동인 출처 — 어느 자료가 어느 변수가 됐나", "headers": ["동인", "출처·값"], "rows": [[k, v] for k, v in prov.items()]})
    blocks.append({"type": "hl", "text": "의사결정 보조(투자자문 아님): " + " / ".join(v2run.decision.lines(r["decision"])) if r.get("decision") else "의사결정 보조 지표 미산출"})
    return {"h2": "밸류에이션 — 맥킨지·IB 방식(v2 엔진)", "blocks": blocks}, r


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("entity")
    ap.add_argument("--merge")
    ap.add_argument("--out")
    ap.add_argument("--draws", type=int, default=3000)
    a = ap.parse_args(argv)
    sec, r = build(a.entity, a.draws)
    if a.merge:
        p = Path(a.merge)
        d = json.loads(p.read_text(encoding="utf-8"))
        d["sections"] = [s for s in d.get("sections") or [] if not s.get("h2", "").startswith("밸류에이션 — 맥킨지")]
        idx = next((i for i, s in enumerate(d["sections"]) if "시나리오" in s.get("h2", "")), len(d["sections"]))
        d["sections"].insert(idx, sec)
        v = d.setdefault("verdict", {})
        v.setdefault("alpha", None)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[v2→리포트] {p} 에 '밸류에이션' 절 병합 (블록 {len(sec['blocks'])}개)")
    if a.out or not a.merge:
        out = Path(a.out or f"{a.entity}_v2_section.json")
        out.write_text(json.dumps(sec, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[v2→리포트] {out}")
    u = r["upside"]
    print(f"  WACC {r['coc']['wacc']:.2%} · 기본 {r['base']['v0']:.2f}배 · MC P50 {u.get('v0_p50') or 0:.2f}배 · 5년 " + " · ".join(f"≥{k:g}배 {p:.0%}" for k, p in (u.get('p_h') or {}).items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
