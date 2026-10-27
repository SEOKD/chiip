"""동인 기반 실적 모델 계산 (BUILD_PROMPT §7.4 model-build)

drivers.csv(period,segment,driver,value,unit,basis,evidence_ids,note) →
segment별 매출 = volume × asp, 매출원가 = volume × cogs_per_unit, 매출총이익
전사 영업이익 = Σ매출총이익 − opex, 세후 영업이익, 단순 FCF = 세후 영업이익 + da − capex
시나리오: driver@bull / driver@bear (없으면 기본 driver 사용)

단위는 사용자가 맞춘다: volume·asp의 곱이 매출 단위가 되도록(예: 백만 개 × 원/개 = 백만 원).
사용: py scripts/model_calc.py <entity> [기본|bull|bear]
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(entity):
    f = ROOT / "knowledge" / "models" / "companies" / entity / "drivers.csv"
    if not f.exists():
        raise SystemExit(f"{f} 없음 — _template/drivers.csv를 복사해 만드세요")
    with f.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def pick(rows, scenario):
    """(period, segment, driver) -> value, 시나리오 값이 있으면 우선"""
    base, scen = {}, {}
    for r in rows:
        drv = r["driver"]
        try:
            val = float(r["value"])
        except ValueError:
            continue
        if "@" in drv:
            d, s = drv.split("@", 1)
            if s == scenario:
                scen[(r["period"], r["segment"], d)] = val
        else:
            base[(r["period"], r["segment"], drv)] = val
    base.update(scen)
    return base


def compute(vals):
    periods = sorted({k[0] for k in vals})
    out = []
    for p in periods:
        segs = sorted({k[1] for k in vals if k[0] == p and k[1] != "전사"})
        gp_total = rev_total = 0.0
        for s in segs:
            vol, asp = vals.get((p, s, "volume")), vals.get((p, s, "asp"))
            if vol is None or asp is None:
                continue
            rev = vol * asp
            cogs = vol * vals.get((p, s, "cogs_per_unit"), 0.0)
            out.append({"period": p, "segment": s, "revenue": rev, "gross_profit": rev - cogs,
                        "operating_profit": "", "nopat": "", "fcf": ""})
            rev_total += rev
            gp_total += rev - cogs
        opex = vals.get((p, "전사", "opex"), 0.0)
        op = gp_total - opex
        tax = vals.get((p, "전사", "tax_rate"), 0.0)
        nopat = op * (1 - tax)
        fcf = nopat + vals.get((p, "전사", "da"), 0.0) - vals.get((p, "전사", "capex"), 0.0)
        out.append({"period": p, "segment": "전사", "revenue": rev_total, "gross_profit": gp_total,
                    "operating_profit": op, "nopat": nopat, "fcf": fcf})
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    entity = argv[0]
    scenario = argv[1] if len(argv) > 1 else "기본"
    rows = compute(pick(load(entity), scenario))
    out = ROOT / "knowledge" / "models" / "companies" / entity / (f"outputs_{scenario}.csv" if scenario != "기본" else "outputs.csv")
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["period", "segment", "revenue", "gross_profit", "operating_profit", "nopat", "fcf"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        if r["segment"] == "전사":
            print(f"{r['period']} 매출 {r['revenue']:,.1f} / 영업이익 {r['operating_profit']:,.1f} / FCF {r['fcf']:,.1f}")
    print(f"저장: {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))