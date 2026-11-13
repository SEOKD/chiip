"""datapack "assets" 초안 — SEC XBRL(companyfacts)에서 자산 구성과 ROIC 원자료를 결정론으로 모은다(마스터 지시 2026-11-13, ADR-021)

리포트 절차(docs/tasks/chiip-tenbagger-report.md)가 부른다. 숫자는 공시 XBRL 값만 쓰고, 없는 칸은 null과 missing 목록('미공시')으로 남긴다.
XBRL 회사 사실 묶음에는 항목별(차원) 값이 없어 유형자산 항목(토지·건물·장비·건설중)과 내용연수 범위, 무형자산 항목은 모델이
10-K 유형자산·무형자산 주석을 읽고 ppe·intangibles에 채운다(채우지 못하면 '미공시' 그대로 — 절은 나머지로 나온다).
사용: py scripts/tenbagger/asset_pack.py <entity_id> [--ticker LTH] [--write] [--force]
  --write: datapack.json의 assets에 쓴다(이미 모델이 채운 칸은 덮지 않는다, --force면 XBRL 칸을 새로 쓴다)
SEC 접속: data.sec.gov, 식별 가능한 User-Agent(radar/pollers/sec_filings._ua — SEC_USER_AGENT), 한 번에 요청 1회.
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:0>10}.json"

C = {   # 개념 후보(먼저 있는 것)
    "rev": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "ebit": ["OperatingIncomeLoss"],
    "da": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "DepreciationAmortizationAndAccretionNet"],
    "dep": ["Depreciation"],
    "amort": ["AmortizationOfIntangibleAssets"],
    "ppe_net": ["PropertyPlantAndEquipmentNet"],
    "ppe_gross": ["PropertyPlantAndEquipmentGross"],
    "ppe_accum": ["AccumulatedDepreciationDepletionAndAmortizationPropertyPlantAndEquipment"],
    "rou": ["OperatingLeaseRightOfUseAsset"],
    "lease_liab": ["OperatingLeaseLiability"],
    "lease_cur": ["OperatingLeaseLiabilityCurrent"],
    "lease_nc": ["OperatingLeaseLiabilityNoncurrent"],
    "lease_rate": ["OperatingLeaseWeightedAverageDiscountRatePercent"],
    "goodwill": ["Goodwill"],
    "intang": ["IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"],
    "intang_gross": ["IntangibleAssetsGrossExcludingGoodwill", "FiniteLivedIntangibleAssetsGross"],
    "intang_accum": ["FiniteLivedIntangibleAssetsAccumulatedAmortization"],
    "gw_impair": ["GoodwillImpairmentLoss"],
    "ar": ["AccountsReceivableNetCurrent"],
    "inv": ["InventoryNet"],
    "prepaid": ["PrepaidExpenseAndOtherAssetsCurrent", "PrepaidExpenseCurrent", "OtherAssetsCurrent"],
    "ap": ["AccountsPayableCurrent"],
    "accrued": ["AccruedLiabilitiesCurrent", "AccountsPayableAndAccruedLiabilitiesCurrent"],
    "deferred_rev": ["ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"],
    "other_a": ["OtherAssetsNoncurrent"],
    "other_l": ["OtherLiabilitiesNoncurrent"],
    "rd": ["ResearchAndDevelopmentExpense"],
    "sga": ["SellingGeneralAndAdministrativeExpense"],
}
NWC_PLUS, NWC_MINUS = ("ar", "inv", "prepaid"), ("ap", "accrued", "deferred_rev")


def fetch(ticker):
    sys.path.insert(0, str(ROOT))
    from radar.pollers import common, sec_filings
    cik = sec_filings.cik_for(ticker, {})
    if not cik:
        raise SystemExit(f"CIK를 찾지 못했다: {ticker}")
    return json.loads(common.http_get(FACTS.format(cik=cik), None, {"User-Agent": sec_filings._ua()}))


def _days(x):
    return (date.fromisoformat(x["end"]) - date.fromisoformat(x["start"])).days if x.get("start") else None


def series(facts, key, kind):
    """kind = 'inst'(시점) → {end: v}, 'q'(분기, 4분기 = 연간 − 1~3분기) → {end: v}, 'y'(연간) → {end: v}. 단위 USD는 백만 달러로"""
    g = (facts.get("facts") or {}).get("us-gaap") or {}
    for concept in C[key]:
        if concept not in g:
            continue
        unit = "pure" if key == "lease_rate" else "USD"
        rows = (g[concept].get("units") or {}).get(unit) or []
        scale = 1.0 if unit == "pure" else 1e-6
        out, fy = {}, {}
        for x in rows:
            d = _days(x)
            if kind == "inst" and d is None:
                out[x["end"]] = x["val"] * scale
            elif kind in ("q", "y") and d is not None:
                if d < 100:
                    out[x["end"]] = x["val"] * scale
                elif d > 350:
                    fy[x["end"]] = x["val"] * scale
        if kind == "y":
            return dict(sorted(fy.items())), concept
        if kind == "q":
            for e, v in fy.items():
                y = e[:4]
                qs = [k for k in out if k[:4] == y and k < e]
                if len(qs) == 3 and e not in out:
                    out[e] = v - sum(out[k] for k in qs)
        if out:
            return dict(sorted(out.items())), concept
    return {}, None


def qlabel(end):
    y, m = int(end[:4]), int(end[5:7])
    return f"{(m - 1) // 3 + 1}Q{str(y)[2:]}"


def _at(s, ends):
    return [round(s[e], 3) if e in s else None for e in ends]


def build(facts, tax=0.25):
    S = {k: series(facts, k, "inst" if k in ("ppe_net", "ppe_gross", "ppe_accum", "rou", "lease_liab", "lease_cur", "lease_nc", "lease_rate", "goodwill",
                                             "intang", "intang_gross", "intang_accum", "ar", "inv", "prepaid", "ap", "accrued", "deferred_rev", "other_a", "other_l")
                            else "q")[0] for k in C}
    Y = {k: series(facts, k, "y")[0] for k in ("dep", "da", "amort", "rd", "sga", "gw_impair")}
    missing = []
    q_ends = sorted(set(S["da"]) & set(S["ppe_net"]))[-9:]
    if len(q_ends) < 5:
        missing.append("분기 감가상각·유형자산(순액) 9분기")
    quarters = [{"q": qlabel(e), "end": e, "da": round(S["da"][e], 3), "ppe_net": round(S["ppe_net"][e], 3),
                 "ppe_gross": round(S["ppe_gross"][e], 3) if e in S["ppe_gross"] else None} for e in q_ends]
    # TTM 두 기간(최근 분기, 1년 전)
    rq = sorted(set(S["rev"]) & set(S["ebit"]))
    roic = None
    if len(rq) >= 8:
        last, prev = rq[-4:], rq[-8:-4]
        ends = [rq[-1], rq[-5], rq[-9] if len(rq) >= 9 else None]
        ends = [e for e in ends if e]
        lease = {e: (S["lease_cur"].get(e) or 0) + (S["lease_nc"].get(e) or 0) for e in set(S["lease_cur"]) & set(S["lease_nc"])}
        lease = {**S["lease_liab"], **lease}   # 합계 칸이 연말에만 있는 회사가 많다 — 분기는 유동 + 비유동

        def nwc(e):
            plus = [S[k].get(e) for k in NWC_PLUS]
            minus = [S[k].get(e) for k in NWC_MINUS]
            if all(v is None for v in plus + minus):
                return None
            return round(sum(v or 0 for v in plus) - sum(v or 0 for v in minus), 3)

        def other(e):
            a, b = S["other_a"].get(e), S["other_l"].get(e)
            return None if a is None and b is None else round((a or 0) - (b or 0), 3)
        cap = {"nwc": [nwc(e) for e in ends], "ppe": _at(S["ppe_net"], ends), "rou": _at(S["rou"], ends), "goodwill": _at(S["goodwill"], ends),
               "intangibles": _at(S["intang"], ends), "other": [other(e) for e in ends]}
        for k, v in list(cap.items()):
            if all(x is None for x in v):
                missing.append({"nwc": "운전자본 항목", "ppe": "유형자산 순액", "rou": "리스 사용권자산", "goodwill": "영업권", "intangibles": "무형자산", "other": "기타 영업자산·부채"}[k])
                cap.pop(k)
            else:
                cap[k] = [x if x is not None else 0.0 for x in v]
        amort_y = list(Y["amort"].values())
        rate = list(S["lease_rate"].values())
        roic = {"periods": [f"TTM {qlabel(rq[-1])}", f"TTM {qlabel(rq[-5])}"],
                "rev": [round(sum(S["rev"][e] for e in last), 3), round(sum(S["rev"][e] for e in prev), 3)],
                "ebit": [round(sum(S["ebit"][e] for e in last), 3), round(sum(S["ebit"][e] for e in prev), 3)],
                "acq_amort": [round(amort_y[-1], 3), round(amort_y[-2] if len(amort_y) > 1 else amort_y[-1], 3)] if amort_y else [0.0, 0.0],
                "tax_rate": tax, "lease_liab": _at(lease, ends) if lease else [], "lease_rate": rate[-1] if rate else None,
                "impairment_cum": round(sum(Y["gw_impair"].values()), 3) if Y["gw_impair"] else 0.0, "capital": cap,
                "note": "SEC 공시 데이터 자동 초안 — 운전자본 = 매출채권 + 재고 + 선급 − (매입채무 + 미지급비용 + 선수수익), 현금 제외. 손상 누계는 공시 데이터 수록분"}
        if not lease:
            missing.append("운영리스 부채")
        if not rate:
            missing.append("리스 가중평균 할인율")
    else:
        missing.append("분기 매출·영업이익 8분기")
    fy = sorted(set(S["ppe_gross"]) & set(S["ppe_accum"]))[-2:][::-1]
    dep_y = Y["dep"] or Y["da"]
    out = {"as_of": qlabel(rq[-1]) if rq else None, "unit": "$M", "source": "SEC 공시 데이터(10-K·10-Q) 자동 초안 — scripts/tenbagger/asset_pack.py",
           "note_periods": fy or None,
           "ppe": [{"name": "유형자산 합계(항목 미분해)", "kind": "other", "gross": [round(S["ppe_gross"][e], 3) for e in fy], "accum": [None] * len(fy), "split": False}] if fy else [],
           "ppe_accum": [round(S["ppe_accum"][e], 3) for e in fy] if fy else None,
           "intangibles": [], "dep_annual": [{"year": int(e[:4]), "dep": round(v, 3), "amort": round(Y["amort"].get(e, 0.0), 3)} for e, v in sorted(dep_y.items())[::-1][:2]],
           "quarters": quarters, "da_note": "손익계산서 감가상각·상각비(SEC 공시 데이터, 4분기 = 연간 − 1~3분기)" + ("" if any(x["ppe_gross"] for x in quarters) else ". 분기 유형자산 총액이 없어 순액 기준"),
           "roic": roic,
           "intangible_cap": {"rd": [[int(e[:4]), round(v, 3)] for e, v in Y["rd"].items()], "sga": [[int(e[:4]), round(v, 3)] for e, v in Y["sga"].items()]} if (Y["rd"] or Y["sga"]) else None,
           "missing": missing + ["유형자산 항목별 총액·내용연수(10-K 주석에서 모델이 채움)", "무형자산 항목(10-K 주석에서 모델이 채움)"]}
    ends_y = sorted(set(S["goodwill"]) & set(fy))[::-1] if fy else []
    if ends_y:
        out["intangibles"].append({"name": "영업권", "kind": "goodwill", "gross": [round(S["goodwill"][e], 3) for e in fy], "accum": [0, 0], "acquired": True})
    if fy and all(e in S["intang_gross"] for e in fy):
        out["intangibles"].append({"name": "무형자산 합계(항목 미분해)", "kind": "finite", "gross": [round(S["intang_gross"][e], 3) for e in fy],
                                   "accum": [round(S["intang_accum"].get(e, 0.0), 3) for e in fy], "acquired": True, "split": False})
    return {k: v for k, v in out.items() if v is not None}


def merge(old, new, force=False):
    """모델이 채운 칸(항목별 ppe·intangibles 등)은 지키고 비어 있는 칸만 채운다"""
    if not old:
        return new
    out = dict(old)
    for k, v in new.items():
        if force and k not in ("ppe", "intangibles", "missing"):
            out[k] = v
        elif out.get(k) in (None, [], {}):
            out[k] = v
    if any(x.get("split") is not False for x in out.get("ppe") or []):   # 모델이 항목을 나눴으면 '미분해' 안내는 뺀다
        out["missing"] = [m for m in out.get("missing") or [] if not m.startswith("유형자산 항목별")]
    if any(x.get("split") is not False and x.get("kind") != "goodwill" for x in out.get("intangibles") or []):
        out["missing"] = [m for m in out.get("missing") or [] if not m.startswith("무형자산 항목")]
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("entity")
    ap.add_argument("--ticker")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    p = ROOT / "knowledge" / "models" / "companies" / a.entity / "datapack.json"
    dp = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    ticker = a.ticker or dp.get("ticker")
    if not ticker:
        raise SystemExit("티커가 없다 — --ticker")
    new = build(fetch(ticker), dp.get("tax", 0.25))
    if a.write and dp:
        dp["assets"] = merge(dp.get("assets"), new, a.force)
        p.write_text(json.dumps(dp, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"[assets] {p} — 미공시: {' · '.join(dp['assets'].get('missing') or []) or '없음'}")
    else:
        print(json.dumps(new, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
