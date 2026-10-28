"""미국 상장·ADR 종목 재무 이력 (BUILD_PROMPT §21.14, ADR-010 §8) — SEC XBRL companyfacts, 키 불필요·무료

data.sec.gov/api/xbrl/companyfacts/CIK##########.json 에서 핵심 계정의 연간(10-K·20-F)·분기(10-Q) 값을
knowledge/models/fundamentals/us/<TICKER>.csv (긴 형식, git 제외 — 다시 받을 수 있음)로 저장한다.
DCF·3표 모델·파라미터 피팅(장기 P/E·P/B–ROE 등)의 무료 재무 재료. 가격·추정치는 별도(TODO 21-0).
SEC 접속 규칙: 식별 가능한 User-Agent(SEC_USER_AGENT), 초당 10회 이하. 미국 정부 자료라 재사용 제한 없음.
사용: py radar/markets/sec_xbrl.py [--ticker NVDA]   (주 1회 정도면 충분 — 분기 보고서 주기)
"""
import argparse
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common, sec_filings  # noqa: E402

FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"
OUT = common.ROOT / "knowledge" / "models" / "fundamentals" / "us"
COLS = ["metric", "concept", "fy", "fp", "form", "start", "end", "filed", "value", "unit"]
# 치입 계정명 → 후보 개념(먼저 있는 것). 외국 발행사(20-F)는 ifrs-full
CONCEPTS = {
    "revenue": ["us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:SalesRevenueNet",
                "ifrs-full:Revenue"],
    "gross_profit": ["us-gaap:GrossProfit", "ifrs-full:GrossProfit"],
    "operating_income": ["us-gaap:OperatingIncomeLoss", "ifrs-full:ProfitLossFromOperatingActivities"],
    "net_income": ["us-gaap:NetIncomeLoss", "ifrs-full:ProfitLossAttributableToOwnersOfParent", "ifrs-full:ProfitLoss"],
    "eps_diluted": ["us-gaap:EarningsPerShareDiluted", "ifrs-full:DilutedEarningsLossPerShare"],
    "rnd": ["us-gaap:ResearchAndDevelopmentExpense", "ifrs-full:ResearchAndDevelopmentExpense"],
    "cfo": ["us-gaap:NetCashProvidedByUsedInOperatingActivities", "ifrs-full:CashFlowsFromUsedInOperatingActivities"],
    "capex": ["us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
              "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"],
    "da": ["us-gaap:DepreciationDepletionAndAmortization", "us-gaap:DepreciationAndAmortization",
           "ifrs-full:DepreciationAndAmortisationExpense"],
    "equity": ["us-gaap:StockholdersEquity", "ifrs-full:EquityAttributableToOwnersOfParent"],
    "total_assets": ["us-gaap:Assets", "ifrs-full:Assets"],
    "cash": ["us-gaap:CashAndCashEquivalentsAtCarryingValue", "ifrs-full:CashAndCashEquivalents"],
    "debt_lt": ["us-gaap:LongTermDebtNoncurrent", "us-gaap:LongTermDebt", "ifrs-full:NoncurrentPortionOfNoncurrentBorrowings"],
    "shares_diluted": ["us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
                       "ifrs-full:AdjustedWeightedAverageShares"],
    "inventory": ["us-gaap:InventoryNet", "ifrs-full:Inventories"],
}
KEEP_FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F"}


def extract(facts):
    """companyfacts JSON → 행 목록. 같은 (계정, 기간 끝, 기간 시작, fp)는 가장 늦게 제출된 값 하나만.
    후보 개념은 앞의 것이 우선 — 뒤 개념은 앞 개념에 없는 기간만 채운다(회사가 분기 중 태그를 바꾼 경우)"""
    rows = {}
    tax = facts.get("facts", {})
    for metric, cands in CONCEPTS.items():
        taken = set()  # 앞 개념이 이미 채운 기간
        for c in cands:
            ns, name = c.split(":")
            node = tax.get(ns, {}).get(name)
            if not node:
                continue
            for unit, vals in node.get("units", {}).items():
                for v in vals:
                    if v.get("form") not in KEEP_FORMS:
                        continue
                    key = (metric, v.get("end"), v.get("start", ""), v.get("fp"))
                    if key in taken:
                        continue
                    if key in rows and rows[key]["filed"] >= v.get("filed", ""):
                        continue
                    rows[key] = {"metric": metric, "concept": c, "fy": v.get("fy"), "fp": v.get("fp"), "form": v.get("form"),
                                 "start": v.get("start", ""), "end": v.get("end"), "filed": v.get("filed", ""),
                                 "value": v.get("val"), "unit": unit}
            taken |= {k for k in rows if k[0] == metric}
    return sorted(rows.values(), key=lambda r: (r["metric"], r["end"], r["start"]))


def run(only=None):
    uni = (common.load_yaml("config/valuation.yaml") or {}).get("universe", [])
    st = common.load_state("sec_filings", {})
    ua = {"User-Agent": sec_filings._ua()}
    OUT.mkdir(parents=True, exist_ok=True)
    done, errors = [], []
    for u in uni:
        tk = sec_filings.ticker_of(u)
        if not tk or (only and tk.upper() != only.upper()):
            continue
        try:
            cik = sec_filings.cik_for(tk, st)
            if not cik:
                errors.append(f"{tk}: CIK 없음")
                continue
            facts = json.loads(common.http_get(FACTS.format(cik=cik), headers=ua, timeout=40))
            rows = extract(facts)
            with (OUT / f"{tk}.csv").open("w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=COLS)
                w.writeheader()
                w.writerows(rows)
            done.append((tk, len(rows)))
        except Exception as exc:
            errors.append(f"{tk}: {type(exc).__name__}")
        time.sleep(0.25)  # 초당 10회 한도보다 넉넉히
    common.save_state("sec_filings", st)
    common.record_health("src-sec-xbrl", bool(done), "; ".join(errors[:5]) or None)
    return done, errors


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker")
    a = ap.parse_args(argv)
    done, errors = run(a.ticker)
    print(f"[SEC 재무] {len(done)}종목 저장" + (f", 실패 {len(errors)}: {'; '.join(errors[:6])}" if errors else ""))
    for tk, n in done[:8]:
        print(f"- {tk}: {n}행")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
