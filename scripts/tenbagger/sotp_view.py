"""Analysis 리포트 'SOTP 사업부 가치' 절 (ADR-016, 마스터 지시 2026-11-07 "삼성전자처럼 사업부가 많은 종목은 SOTP를 적용")

scripts/valuation/v2/sotp.py --save 결과(knowledge/models/valuation/v2/<id>_sotp.json)가 있는 종목만 그린다.
사업부 가치 폭포 그림은 report_layout이 한눈에 보기로 옮긴다. 목표주가가 아니라 시가총액 대비 배수로만 쓴다.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2 = ROOT / "knowledge" / "models" / "valuation" / "v2"


def load(eid):
    p = V2 / f"{eid}_sotp.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def section(eid):
    r = load(eid)
    if not r:
        return None
    sc = r.get("_scale") or 1
    lab = r.get("_scale_label") or r.get("unit", "")
    f = lambda x: f"{x / sc:,.1f}" if x is not None else "—"
    head = (f"**사업부 가치 합산(SOTP) 주주가치는 시가총액의 {r['x_mcap']:.2f}배**(사업부 DCF 기준, 동종사 배수 기준 {r['x_mcap_multiples']:.2f}배)."
            + (f" 몬테카를로 P10 {r['mc']['p10']:.2f} · P50 {r['mc']['p50']:.2f} · P90 {r['mc']['p90']:.2f}배." if (r.get("mc") or {}).get("n") else ""))
    rows = []
    for s in r["segments"]:
        me = f"{f(s['mult_ev'])}({s['mult']:.1f}배 {'매출' if s['mult_metric'] == 'sales' else 'EBIT'})" if s.get("mult_ev") is not None else "—"
        rows.append([s["name"], f"{s['wacc']:.1%}", f(s["dcf_ev"]), me, f"{s['ev'] / r['equity']:.0%}" if r["equity"] else "—",
                     f"{s['normal_margin']:.1%}" if s.get("normal_margin") is not None else "—"])
    B = [{"type": "hl", "text": head},
         {"type": "table", "title": f"사업부별 가치({lab})", "headers": ["사업부", "WACC", "DCF 가치", "동종사 배수 가치", "주주가치 비중", "정상화 마진"], "rows": rows},
         {"type": "p", "text": f"사업부 합 {f(r['seg_sum'])} − 소수지분 {f(r['minority'])} − 본사 비용 {f(r['hq_cap'])} + 순현금 {f(r['net_cash'])} + 상장 지분 {f(r['stakes_total'])}"
                               f"(시가 × (1 − 지주 할인 {r['holding_discount']:.0%})) = 주주가치 {f(r['equity'])}{lab}. 지주 할인 민감도: "
                               + " · ".join(f"{k} {v:.2f}배" for k, v in (r.get("discount_sensitivity") or {}).items()) + "."}]
    if r.get("chart"):
        B.append({"type": "chart", "chart": r["chart"]})   # report_layout이 한눈에 보기로 옮긴다
    warn = [f"{s['name']} — {s['exit_warn']}" for s in r["segments"] if s.get("exit_warn")]
    if warn:
        B.append({"type": "p", "text": "**출구 배수 점검:** " + "; ".join(warn)})
    B.append({"type": "p", "text": "사업부 매출·이익은 회사 IR 공시, 동종사 배수는 시세 원천의 EV ÷ 실적. 영업이익을 공시하지 않는 사업부는 가정값이라 신뢰도가 낮다. 공개 자료 기반 분석이며 투자 권유가 아님."})
    return {"h2": "SOTP 사업부 가치", "blocks": B}
