"""SOTP(사업부별 가치 합산) — ADR-016 3-1, 마스터 지시 2026-11-07 "삼성전자처럼 사업부가 많은 종목은 SOTP를 적용"

입력: knowledge/models/companies/<id>/sotp.yaml (사업부·상장 지분·순현금·소수지분), 설정 config/valuation_v3.yaml sotp.
사업부 가치 = ① 사업부 DCF(사업부 업종 베타로 WACC, D2·D3·D6 보강 그대로) ② 동종사 배수(EV/EBIT 또는 EV/Sales 중앙값) — 둘 다 낸다.
주주가치 = Σ 사업부(주 방식) − 소수지분 몫 − 본사 비용(연 비용 ÷ (WACC − g)) + 순현금 + Σ 상장 지분 × 시가 × (1 − 지주 할인) + 비상장 지분(장부가)
몬테카를로: 사업부 충격 = √ρ·공통 + √(1−ρ)·고유 (ρ = sotp.corr_segments), 성장·마진 충격 상관(D4)
금액 단위는 sotp.yaml unit 하나(삼성전자: 10억 원). 목표주가가 아니라 시가총액 대비 배수로만 표기한다.
사용: py scripts/valuation/v2/sotp.py <entity_id> [--save]
"""
import argparse
import json
import math
import random
import statistics
import sys
from datetime import date
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import dcf  # noqa: E402
import montecarlo  # noqa: E402
import plus  # noqa: E402
import regime as regime_mod  # noqa: E402
import scenarios  # noqa: E402

OUT = ROOT / "knowledge" / "models" / "valuation" / "v2"
DISCLAIMER = "공개 자료 기반 분석이며 투자 권유가 아님"


def load(entity):
    return yaml.safe_load((ROOT / "knowledge" / "models" / "companies" / entity / "sotp.yaml").read_text(encoding="utf-8"))


def seg_wacc(reg, industry, region_mix, tax):
    """업종 평균 자본 구조로 본 사업부 WACC(사업부는 자기 부채가 없으니 업종 부채비율을 쓴다 — McKinsey 사업부 할인율 관행)"""
    ind = reg["industry"][industry]
    rf, erp = reg["rf_us"], reg["erp"]
    crp = sum(w * reg["crp"].get(r, 0.0) for r, w in region_mix.items())
    ke = rf + ind["beta"] * erp + crp
    kd = rf + 0.015
    ew = ind["equity_weight"]
    return ew * ke + (1 - ew) * kd * (1 - tax)


def seg_drivers(seg, co, wacc, g_term):
    """사업부 사양 → dcf 동인(dict). 주식 수 1·순차입 0 — 가치는 EV"""
    c = {"rev0": seg["rev0"], "unit_usd": co.get("unit_usd", 1e9), "tax": co["tax"], "ic0": seg.get("ic0", seg["rev0"] / seg["s2c"]),
         "horizon": co.get("horizon", 10), "market": {"net_debt": 0.0, "shares": 1.0}, "midyear": co.get("midyear", True),
         "cyclical": seg.get("cyclical"), "moat_score": seg.get("moat"), "ronic_spread": seg.get("ronic_spread")}
    return c, scenarios.drivers(c, {"growth": seg["growth"], "margin": seg["margin"], "s2c": seg["s2c"]}, wacc, g_term)


def seg_multiple(seg):
    """(EV, 배수 중앙값, 지표 값) — 지표: ebit = rev0 × 정상 마진(지정 시) 또는 현재 마진, sales = rev0"""
    m = seg.get("multiple")
    if not m:
        return None, None, None
    peers = [float(v) for v in (m.get("peers") or {}).values() if v is not None]
    if not peers:
        return None, None, None
    mult = statistics.median(peers)
    if m["metric"] == "sales":
        base = seg["rev0"]
    else:
        base = seg["rev0"] * float(m.get("margin", seg.get("margin0", 0.0)))
    return mult * base, mult, base


def stakes_value(co, disc):
    rows, total = [], 0.0
    for s in co.get("stakes") or []:
        mv = s["shares"] * s["price"] / co.get("price_scale", 1.0)
        rows.append({"name": s["name"], "market_value": mv, "after_discount": mv * (1 - disc), "pct": s.get("pct")})
        total += mv * (1 - disc)
    return total, rows


def evaluate(entity, reg=None, draws=None):
    co = load(entity)
    c3 = plus.cfg()
    sc = c3["sotp"]
    reg = reg or regime_mod.load() or regime_mod.build()
    if co.get("rf_local"):
        reg = {**reg, "rf_us": co["rf_local"]}
    g_term = co.get("g_term", 0.03)
    mcap = co["market"]["price"] * co["market"]["shares"]
    segs = []
    for s in co["segments"]:
        w = seg_wacc(reg, s["industry"], s.get("region_mix") or co["region_mix"], co["tax"])
        cco, d = seg_drivers(s, co, w, g_term)
        v = dcf.value(d)
        ex_mult, ex_rng, ex_warn = plus.exit_check(v, d, s["industry"], c3)
        nm, nm_src = plus.normal_margin(s.get("cyclical"))
        mev, mult, mbase = seg_multiple(s)
        dcf_ev = v["ev"]
        main = s.get("method", "dcf")
        ev = dcf_ev if main == "dcf" or mev is None else mev
        segs.append({"name": s["name"], "parent": s.get("parent"), "wacc": w, "dcf_ev": dcf_ev, "mult_ev": mev, "mult": mult, "mult_metric": (s.get("multiple") or {}).get("metric"),
                     "mult_base": mbase, "ev": ev, "method": main, "minority": float(s.get("minority", 0.0)), "rev0": s["rev0"], "margin0": s.get("margin0"),
                     "normal_margin": nm, "normal_src": nm_src, "exit_ev_ebit": ex_mult, "exit_warn": ex_warn, "cv_share": v["cv_share"], "ronic": d.get("ronic"),
                     "note": s.get("note", "")})
    hq = co.get("hq_cost", 0.0)
    hq_cap = hq / (statistics.mean(s["wacc"] for s in segs) - g_term) if hq else 0.0
    minority = sum(s["ev"] * s["minority"] for s in segs)
    disc = float(sc["holding_discount"])
    stk, stk_rows = stakes_value(co, disc)
    unlisted = sum(u.get("book", 0.0) for u in co.get("unlisted") or [])
    net_cash = -co["market"]["net_debt"]
    seg_sum = sum(s["ev"] for s in segs)
    equity = seg_sum - minority - hq_cap + net_cash + stk + unlisted
    sens = {}
    for dd in (0.0, disc, 0.5):
        sens[f"{dd:.0%}"] = (equity - stk + stakes_value(co, dd)[0]) / mcap
    alt = sum(s["mult_ev"] if s["mult_ev"] is not None else s["dcf_ev"] for s in segs) - sum((s["mult_ev"] if s["mult_ev"] is not None else s["dcf_ev"]) * s["minority"] for s in segs) - hq_cap + net_cash + stk + unlisted
    mc = simulate(co, segs, reg, g_term, draws or sc["draws"], sc["seed"], float(sc["corr_segments"]), c3, equity - seg_sum + minority)
    return {"entity": entity, "name": co["name"], "as_of": date.today().isoformat(), "drivers_as_of": str(co.get("as_of", "")), "unit": co.get("unit", ""),
            "mcap": mcap, "market": co["market"], "segments": segs, "seg_sum": seg_sum, "minority": minority, "hq_cap": hq_cap, "net_cash": net_cash,
            "stakes": stk_rows, "stakes_total": stk, "holding_discount": disc, "unlisted": unlisted, "equity": equity, "x_mcap": equity / mcap,
            "x_mcap_multiples": alt / mcap, "discount_sensitivity": sens, "mc": mc, "notes": co.get("notes", []), "evidence": co.get("evidence", []),
            "conglomerate_check": co.get("conglomerate_check")}


def simulate(co, segs, reg, g_term, draws, seed, rho, c3, rest):
    """사업부 DCF 몬테카를로 — 공통 요인 상관. rest = 사업부 밖 항목(순현금·지분 − 본사 비용, 소수지분은 사업부별로 뺀다)"""
    rng = random.Random(seed)
    cc = c3.get("mc_corr") or {}
    rgm, df = float(cc.get("rho_growth_margin", 0.4)), cc.get("t_df")
    mcap = co["market"]["price"] * co["market"]["shares"]
    specs = {s["name"]: s for s in co["segments"]}
    out, dropped = [], 0
    for _ in range(draws):
        common = montecarlo.t_unit(rng, df)
        total = rest
        try:
            for sg in segs:
                s = specs[sg["name"]]
                if sg["method"] != "dcf":
                    total += sg["ev"] * (1 - sg["minority"])
                    continue
                z = math.sqrt(rho) * common + math.sqrt(1 - rho) * montecarlo.t_unit(rng, df)
                zm = rgm * z + math.sqrt(1 - rgm * rgm) * montecarlo.t_unit(rng, df)
                sig = s.get("mc") or {}
                _, d = seg_drivers(s, co, sg["wacc"] + rng.gauss(0, sig.get("sigma_wacc", 0.005)), g_term)
                d["growth"] = [max(-0.9, g + (sig.get("sigma_growth", 0.05) * z if i == 0 else 0.0) * (sig.get("decay", 0.6) ** i)) for i, g in enumerate(d["growth"])]
                d["margin"] = [m + sig.get("sigma_margin", 0.03) * zm for m in d["margin"]]
                if d["wacc"] <= d["g_term"] + 0.01:
                    raise ValueError
                total += dcf.value(d)["ev"] * (1 - sg["minority"])
        except (ValueError, ZeroDivisionError, OverflowError):
            dropped += 1
            continue
        out.append(total / mcap)
    if not out:
        return {"n": 0, "dropped": dropped}
    q = lambda p: montecarlo.quantile(out, p)
    return {"n": len(out), "dropped": dropped, "p10": q(0.1), "p50": q(0.5), "p90": q(0.9), "mean": sum(out) / len(out),
            "p_below_1": sum(1 for x in out if x < 1) / len(out)}


def waterfall(r):
    """사업부 가치 폭포 — 리포트 한눈에 보기(kind waterfall, 단위: 조 원 등 sotp.yaml chart_scale)"""
    steps = [{"label": s["name"], "value": round(s["ev"] / r.get("_scale", 1), 1), "kind": "cost"} for s in r["segments"]]
    if r["minority"]:
        steps.append({"label": "소수지분", "value": -round(r["minority"] / r.get("_scale", 1), 1), "kind": "cost"})
    if r["hq_cap"]:
        steps.append({"label": "본사 비용", "value": -round(r["hq_cap"] / r.get("_scale", 1), 1), "kind": "cost"})
    steps.append({"label": "순현금", "value": round(r["net_cash"] / r.get("_scale", 1), 1), "kind": "cost"})
    if r["stakes_total"]:
        steps.append({"label": f"상장 지분(−{r['holding_discount']:.0%})", "value": round(r["stakes_total"] / r.get("_scale", 1), 1), "kind": "cost"})
    steps.append({"label": "주주가치", "value": round(r["equity"] / r.get("_scale", 1), 1), "kind": "total"})
    steps.append({"label": "시가총액", "value": round(r["mcap"] / r.get("_scale", 1), 1), "kind": "total"})
    return {"kind": "waterfall", "title": f"SOTP 사업부 가치 합산({r.get('_scale_label', r['unit'])})", "steps": steps}


def render(r):
    u = r["unit"]
    L = [f"[모드: invest / 범위: {r['name']} SOTP / 기준시각: {r['as_of']} KST]", "",
         f"## {r['name']} — 사업부 가치 합산 (시가총액 {r['mcap']:,.0f}{u} 대비)",
         f"- 주주가치 {r['equity']:,.0f}{u} = 시가총액의 **{r['x_mcap']:.2f}배**(사업부 DCF 기준) · 동종사 배수 기준 {r['x_mcap_multiples']:.2f}배",
         "", "| 사업부 | WACC | DCF EV | 배수 EV(배수) | 채택 | 소수지분 | 정상화 마진 | 출구 EV/EBIT |", "|---|---|---|---|---|---|---|---|"]
    for s in r["segments"]:
        me = f"{s['mult_ev']:,.0f}({s['mult']:.1f}× {s['mult_metric']})" if s["mult_ev"] is not None else "—"
        nm = f"{s['normal_margin']:.1%}" if s["normal_margin"] is not None else "—"
        ex = (f"{s['exit_ev_ebit']:.1f}" + (" ⚠" if s["exit_warn"] else "")) if s["exit_ev_ebit"] else "—"
        L.append(f"| {s['name']} | {s['wacc']:.1%} | {s['dcf_ev']:,.0f} | {me} | {s['method']} | {s['minority']:.1%} | {nm} | {ex} |")
    L += [f"- 소수지분 −{r['minority']:,.0f} · 본사 비용 −{r['hq_cap']:,.0f} · 순현금 +{r['net_cash']:,.0f} · 상장 지분 +{r['stakes_total']:,.0f}(시가 × (1 − {r['holding_discount']:.0%})) · 비상장 +{r['unlisted']:,.0f}",
          "- 지주 할인 민감도(주주가치/시총): " + " · ".join(f"{k} {v:.2f}배" for k, v in r["discount_sensitivity"].items())]
    m = r["mc"]
    if m.get("n"):
        L.append(f"- 몬테카를로 {m['n']:,}회(사업부 공통 요인 상관, 제외 {m['dropped']}): P10 {m['p10']:.2f} · P50 {m['p50']:.2f} · P90 {m['p90']:.2f}배 · 시총 미만 확률 {m['p_below_1']:.0%}")
    if r.get("conglomerate_check"):
        L.append(f"- 복합기업 점검: {r['conglomerate_check']}")
    for s in r["segments"]:
        if s["exit_warn"] or s["note"]:
            L.append(f"- {s['name']}: " + " · ".join(x for x in (s["note"], s["exit_warn"], s["normal_src"]) if x))
    if r["notes"]:
        L += ["", "**가정 메모**"] + [f"- {x}" for x in r["notes"]]
    if r["evidence"]:
        L += ["", "**근거**"] + [f"- {x}" for x in r["evidence"]]
    L += ["", DISCLAIMER]
    return "\n".join(L)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("entity")
    ap.add_argument("--draws", type=int)
    ap.add_argument("--save", action="store_true")
    a = ap.parse_args(argv)
    r = evaluate(a.entity, draws=a.draws)
    co = load(a.entity)
    r["_scale"], r["_scale_label"] = co.get("chart_scale", 1), co.get("chart_scale_label", r["unit"])
    r["chart"] = waterfall(r)
    print(render(r))
    if a.save:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / f"{a.entity}_sotp.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        od = ROOT / "outputs" / "invest" / "valuation_v2"
        od.mkdir(parents=True, exist_ok=True)
        (od / f"{date.today().strftime('%Y%m%d')}_{a.entity}_sotp.md").write_text(render(r), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
