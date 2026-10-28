"""밸류에이션 v2 실행기 — 종목 drivers.yaml → 할인율·DCF·EP 검증·시나리오·몬테카를로·기대 역산·상승여력 블록

사용: py scripts/valuation/v2/run.py <entity_id> [--draws 5000] [--save]
출력: 비공개 카드(목표주가·투자의견 없음 — 모든 가치는 시가총액 대비 배수와 확률로만 표기)
저장(--save): knowledge/models/valuation/v2/<id>.json, outputs/invest/valuation_v2/YYYYMMDD_<id>.md
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import baserates  # noqa: E402
import dcf  # noqa: E402
import montecarlo  # noqa: E402
import regime as regime_mod  # noqa: E402
import scenarios  # noqa: E402
import upside  # noqa: E402
import wacc as wacc_mod  # noqa: E402

DISCLAIMER = "공개 자료 기반 분석이며 투자 권유가 아님"


def load_company(entity):
    return yaml.safe_load((ROOT / "knowledge" / "models" / "companies" / entity / "drivers.yaml").read_text(encoding="utf-8"))


def evaluate(entity, draws=None, reg=None, cfg=None):
    cfg = cfg or yaml.safe_load((ROOT / "config" / "valuation_v2.yaml").read_text(encoding="utf-8"))
    reg = reg or regime_mod.load() or regime_mod.build()
    co = load_company(entity)
    m = co["market"]
    mcap = m["price"] * m["shares"]
    coc = wacc_mod.cost_of_capital(reg, co["industry"], co["region_mix"], mcap, m["net_debt"], co["tax"],
                                   co.get("pretax_kd"), cfg["defaults"]["pretax_cost_of_debt_spread"])
    region = max(co["region_mix"], key=co["region_mix"].get)
    g_term = co.get("g_term", cfg["defaults"]["g_term"].get(region, 0.03))
    base_d = scenarios.drivers(co, co["scenarios"]["base"], coc["wacc"], g_term)
    base = dcf.value(base_d)
    scen = {}
    for name, sc in co["scenarios"].items():
        d = scenarios.drivers(co, sc, coc["wacc"], g_term)
        scen[name] = {"prob": sc.get("prob"), "v0": dcf.value(d)["equity"] / mcap, "v5": dcf.equity_at(d, 5) / mcap,
                      "cagr5": __import__("pie").cagr(d, 5)}
    mc = montecarlo.simulate(co, coc["wacc"], g_term, cfg["upside"]["horizon_years"],
                             draws or cfg["defaults"]["mc_draws"], cfg["defaults"]["mc_seed"])
    sample = baserates.windows(5)
    blk = upside.block(co, base_d, mc, mcap, cfg["upside"], sample)
    rs = dcf.rate_sensitivity(base_d)
    return {"entity": entity, "name": co["name"], "as_of": date.today().isoformat(), "market": m, "mcap": mcap, "coc": coc,
            "g_term": g_term, "base": {"v0": base["equity"] / mcap, "cv_share": base["cv_share"], "ep_gap": base["ep_gap"],
                                       "roic_y1": base["rows"][0]["roic"], "roic_y5": base["rows"][4]["roic"]},
            "scenarios": scen, "upside": blk, "rate_50bp": rs, "regime": {"rf": reg["rf_us"], "erp": reg["erp"], "as_of": reg["as_of"]},
            "unit": co.get("unit", ""), "evidence": co.get("evidence", []), "notes": co.get("notes", [])}


def _pct(t):
    if not t or t[0] is None:
        return f"백분위 미산정({t[3] if t else ''})"
    return f"기저율 상위 {100 - t[0]:.0f}% (n={t[1]}, {t[2]})"


def render(r):
    u, c, b = r["upside"], r["coc"], r["base"]
    L = [f"[모드: invest / 범위: {r['name']} 밸류에이션 v2 정량 블록(1단계 시험) / 기준시각: {r['as_of']} KST]", "",
         f"## {r['name']} — 가치 분포와 필요 가정 (시가총액 {r['mcap']:.1f}{r['unit']} 대비 배수)",
         f"- 할인율: WACC {c['wacc']:.2%} = 무위험 {c['rf']:.2%}(미 10년) + 베타 {c['beta']:.2f} × ERP {c['erp']:.2%} + 국가위험 {c['crp']:.2%} · 부채비중 {c['debt_weight']:.0%} · 영구성장 {r['g_term']:.1%}",
         f"- 기본 시나리오: 내재가치 {b['v0']:.2f}배 · 계속가치 비중 {b['cv_share']:.0%} · ROIC 1년차 {b['roic_y1']:.0%} → 5년차 {b['roic_y5']:.0%} · EP 항등 오차 {b['ep_gap']:.1e}",
         "", "| 시나리오 | 확률 | 지금 가치/시총 | 5년 뒤 가치/시총 | 5년 매출 CAGR |", "|---|---|---|---|---|"]
    for n, s in r["scenarios"].items():
        L.append(f"| {n} | {s['prob']:.0%} | {s['v0']:.2f} | {s['v5']:.2f} | {s['cagr5']:.1%} |")
    if u.get("v0_p50") is not None:
        ph = " · ".join(f"≥{k:g}배 {p:.0%}" for k, p in u["p_h"].items())
        L += ["", f"**몬테카를로 {u['n']:,}회**(제외 {u['dropped']}): 지금 가치/시총 P10 {u['v0_p10']:.2f} · P50 {u['v0_p50']:.2f} · P90 {u['v0_p90']:.2f} · 기대 {u['v0_mean']:.2f}",
              f"- 5년 뒤 가치가 현재 시총의 {ph}",
              f"- 지금 30% 이상 고평가일 확률 {u['p_over_30pct_overvalued']:.0%} · 비대칭(5년 기대 상방/하방) {u['asymmetry']:.2f}",
              f"- 시장 내포 5년 매출 CAGR {u['implied_cagr']:.1%} → {_pct(u['implied_pct'])}" if u.get("implied_cagr") is not None else "- 시장 내포 CAGR: 역산 불가",
              f"- 우리 기본 시나리오 5년 CAGR {u['base_cagr']:.1%} → {_pct(u['base_pct'])}"]
        for mult, (rc, pt) in u["required"].items():
            L.append(f"- 5년 뒤 {mult}배에 필요한 매출 CAGR(기본 마진 유지) {rc:.1%} → {_pct(pt)}" if rc is not None else f"- {mult}배 필요 CAGR: 역산 불가(마진·재투자 가정으로 도달 불가)")
        L.append(f"- 금리 민감도: 할인율 +50bp → 가치 {r['rate_50bp']['chg']:+.1%} (듀레이션 약 {r['rate_50bp']['duration']:.0f}년)")
        L.append(f"- 알파 정량 제안(병목 제외): " + ", ".join(f"{k} {v}" for k, v in u["alpha"].items()))
    if r["notes"]:
        L += ["", "**가정 메모**"] + [f"- {x}" for x in r["notes"]]
    if r["evidence"]:
        L += ["", "**근거**"] + [f"- {x}" for x in r["evidence"]]
    L += ["", f"시장 체제: 미 10년 {r['regime']['rf']:.2%}, ERP {r['regime']['erp']:.2%} ({r['regime']['as_of']}). 시가·주식수 출처: {r['market'].get('source', '')}",
          "", DISCLAIMER]
    return "\n".join(L)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("entity")
    ap.add_argument("--draws", type=int)
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args(argv)
    r = evaluate(a.entity, a.draws)
    text = render(r)
    print(text)
    if a.save:
        jd = ROOT / "knowledge" / "models" / "valuation" / "v2"
        jd.mkdir(parents=True, exist_ok=True)
        (jd / f"{a.entity}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        od = ROOT / "outputs" / "invest" / "valuation_v2"
        od.mkdir(parents=True, exist_ok=True)
        (od / f"{date.today().strftime('%Y%m%d')}_{a.entity}.md").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
