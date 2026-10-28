"""M1 재무 재구성 (McKinsey 방식, 1단계 근사) — SEC XBRL 긴 형식(knowledge/models/fundamentals/us/<T>.csv) → 연간 지표

1단계 한계(데이터 범위 때문): 투하자본은 조달 측 근사(자기자본 + 장기차입 − 현금, 유동성 차입·리스 미포함),
FCF는 영업현금흐름 − CAPEX(이자 미조정), EBITA 대신 영업이익. EODHD 연결 후 영업 측 투하자본으로 교체.
보정: R&D 자본화(선택, 업종 상각 연수) — 현금흐름은 그대로, 이익·투하자본·ROIC만 바뀐다(Lev·Srivastava, Damodaran).
"""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FUND = ROOT / "knowledge" / "models" / "fundamentals" / "us"


def annual(ticker):
    """{연도: {지표: 값}} — 10-K/20-F 회계연도(fp=FY) 값. 기간 지표는 12개월(±20일)만, 잔액 지표는 기말"""
    p = FUND / f"{ticker}.csv"
    if not p.exists():
        return {}
    out = {}
    with p.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r["fp"] != "FY" or not r["form"].startswith(("10-K", "20-F", "40-F")):
                continue
            yr = int(r["end"][:4])
            if r["start"]:
                from datetime import date
                d0, d1 = date.fromisoformat(r["start"]), date.fromisoformat(r["end"])
                if not 345 <= (d1 - d0).days <= 385:
                    continue
            try:
                out.setdefault(yr, {})[r["metric"]] = float(r["value"])
            except ValueError:
                continue
    return dict(sorted(out.items()))


def metrics(years, tax=0.21, rnd_life=None):
    """연도별 NOPAT·IC·ROIC·FCF·마진. rnd_life를 주면 R&D 자본화 보정"""
    rows, ys = {}, sorted(years)
    research_asset = {}
    if rnd_life:
        for y in ys:   # 연구자산 = 지난 n년 R&D의 미상각 잔액(정액)
            ra, amort = 0.0, 0.0
            for k in range(rnd_life):
                v = years.get(y - k, {}).get("rnd")
                if v is None:
                    continue
                ra += v * (1 - k / rnd_life)
                amort += v / rnd_life
            research_asset[y] = (ra, amort)
    prev_ic = None
    for y in ys:
        d = years[y]
        rev, ebit = d.get("revenue"), d.get("operating_income")
        if rev is None or ebit is None:
            continue
        if rnd_life and d.get("rnd") is not None:
            ra, amort = research_asset[y]
            ebit = ebit + d["rnd"] - amort
        else:
            ra = 0.0
        nopat = ebit * (1 - tax)
        ic = None
        if d.get("equity") is not None:
            ic = d["equity"] + (d.get("debt_lt") or 0.0) - (d.get("cash") or 0.0) + ra
        roic = nopat / ((ic + prev_ic) / 2) if ic and prev_ic and (ic + prev_ic) > 0 else None
        fcf = d["cfo"] - d["capex"] if d.get("cfo") is not None and d.get("capex") is not None else None
        rows[y] = {"revenue": rev, "ebit": ebit, "margin": ebit / rev if rev else None, "nopat": nopat, "ic": ic,
                   "roic": roic, "fcf": fcf, "sales_to_capital": rev / ic if ic and ic > 0 else None}
        prev_ic = ic
    return rows


def incremental_s2c(rows, n=3):
    """최근 n년 증분 매출 ÷ 증분 투하자본 (재투자 효율 사전값). 음수·결측이면 None"""
    ys = [y for y in sorted(rows) if rows[y]["ic"] is not None]
    if len(ys) < n + 1:
        return None
    a, b = rows[ys[-1 - n]], rows[ys[-1]]
    d_ic = b["ic"] - a["ic"]
    d_rev = b["revenue"] - a["revenue"]
    return d_rev / d_ic if d_ic > 0 and d_rev > 0 else None
