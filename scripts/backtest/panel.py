"""월말 요인 패널 복원 (ADR-016 §2-3) — frames(재무, 시점 복원) + 승인된 일봉 원천(가격·수익률)

fundamentals_asof(d): d에 '알려진' 연간·분기 값(frames.known_at ≤ d)으로 회사별 최신 값을 만든다.
build(): 월말마다 요인(알파 v2와 같은 정의) + 이후 h개월 초과수익(fwd)을 붙여 [{date, id, …}] 패널을 낸다.
가격이 필요한 요인(FCF 수익률·B/M·EV/EBIT·규모·모멘텀)과 fwd는 prices.monthly — 원천 승인 전에는 PriceSourceNotApproved.
생존 편향: CIK → 티커는 SEC company_tickers.json(현재 상장사)이라 상장 폐지 종목이 빠진다 — 결과에 표기, 상장 폐지 포함 원천 승인 시 교체.
"""
import math
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import frames  # noqa: E402
import prices  # noqa: E402

FLOW = ("revenue", "operating_income", "da", "cfo", "capex")


def month_ends(start, end):
    out = []
    y, m = int(start[:4]), int(start[5:7])
    while True:
        nm = date(y + (m == 12), m % 12 + 1, 1)
        d = date.fromordinal(nm.toordinal() - 1)
        if d.isoformat() > end:
            return out
        out.append(d.isoformat())
        y, m = nm.year, nm.month


def _series(metric, c):
    """{cik: [(known_at, end, val, kind)]} — 캐시된 frames에서(없으면 빈 것)"""
    out = {}
    for kind, per in frames.periods(int(c["period"]["start"][:4]) - 2, int(c["period"]["end"][:4])):
        if (metric in frames.INSTANT) != (kind == "instant"):
            continue
        if metric in FLOW and kind != "annual":
            continue   # 1단계는 연간 흐름값만(분기 TTM 합산은 다음 단계)
        for tag in c["sec_frames"]["concepts"][metric]:
            p = frames.CACHE / f"{tag.replace(':', '_')}_{per}.csv"
            if not p.exists():
                continue
            import csv
            with p.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
            if not rows:
                continue
            for r in rows:
                out.setdefault(r["cik"], []).append((frames.known_at(r["end"], kind, c["sec_frames"]["lag_days"]), r["end"], float(r["val"]), kind))
            break
    for v in out.values():
        v.sort()
    return out


def fundamentals_asof(d, series):
    """{cik: {metric: (최신 값, 직전 값)}} — d에 알려진 것만"""
    dd = date.fromisoformat(d)
    out = {}
    for metric, by in series.items():
        for cik, rows in by.items():
            known = [r for r in rows if r[0] <= dd]
            if known:
                prev = known[-2][2] if len(known) >= 2 else None
                out.setdefault(cik, {})[metric] = (known[-1][2], prev)
    return out


def fundamental_factors(f, tax=0.21):
    """가격 없이 되는 요인 — 자산 증가율·Inv 더미(Yartseva)·ROA형 수익성. 가격 요인은 add_price_factors"""
    out = {}
    a, oi, da = f.get("total_assets"), f.get("operating_income"), f.get("da")
    if a and a[1]:
        out["asset_growth"] = a[0] / a[1] - 1
        if oi and da and oi[1] is not None and da[1] is not None:
            e0, e1 = oi[1] + da[1], oi[0] + da[0]
            if e0 > 0:
                out["inv_dummy"] = 1.0 if out["asset_growth"] > e1 / e0 - 1 else 0.0
    if a and oi and a[0]:
        out["roic"] = oi[0] * (1 - tax) / a[0]
    return out


def add_price_factors(row, f, px, i, tax=0.21):
    """px = [(월말, 종가)], i = 이번 월말 위치. 시가총액 = 종가 × 주식 수(frames dei)"""
    p = px[i][1]
    sh = (f.get("shares") or (None,))[0]
    if sh and p:
        mcap = p * sh
        row["log_mcap"] = math.log(mcap)
        eq = (f.get("equity") or (None,))[0]
        if eq is not None:
            row["book_to_market"] = eq / mcap
        oi, da, cx = (f.get("operating_income") or (None,))[0], (f.get("da") or (None,))[0], (f.get("capex") or (None,))[0]
        if oi is not None and da is not None and cx is not None:
            row["fcf_yield"] = (oi * (1 - tax) + da - cx) / mcap
        if oi is not None:
            row["ebit_ev"] = oi / mcap   # 순부채 frames 미집계 — 1단계는 시가총액 분모(표기)
    if i >= 12:
        row["mom_12_1"] = px[i - 1][1] / px[i - 12][1] - 1
        win = [x for _, x in px[i - 11:i + 1]]
        hi, lo = max(win), min(win)
        row["price_range"] = (p - lo) / (hi - lo) if hi > lo else None
    if i >= 6:
        row["mom_6m"] = p / px[i - 6][1] - 1
    return row


def build(tickers, horizon=12, bench="SPY", log=print):
    """tickers: {cik: ticker}. 원천 미승인이면 PriceSourceNotApproved"""
    c = frames.cfg()
    series = {m: _series(m, c) for m in c["sec_frames"]["concepts"]}
    ends = month_ends(c["period"]["start"], c["period"]["end"])
    bpx = dict(prices.monthly(bench, ends[0], ends[-1]))
    panel = []
    for cik, tk in tickers.items():
        try:
            px = prices.monthly(tk, ends[0], ends[-1])
        except prices.PriceSourceNotApproved:
            raise
        except Exception as e:   # 개별 종목 실패는 건너뛴다
            log(f"- {tk}: {e}")
            continue
        dates = [d for d, _ in px]
        for i, (d, p) in enumerate(px):
            if i + horizon >= len(px) or d not in bpx or dates[i + horizon] not in bpx:
                continue
            f = fundamentals_asof(d, {m: {cik: series[m].get(cik, [])} for m in series}).get(cik, {})
            row = {"date": d[:7], "id": tk, **fundamental_factors(f)}
            add_price_factors(row, f, px, i)
            row["fwd"] = (px[i + horizon][1] / p) - (bpx[dates[i + horizon]] / bpx[d])
            panel.append(row)
    return panel
