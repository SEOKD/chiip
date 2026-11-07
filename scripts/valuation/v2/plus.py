"""DCF 보강 D2·D3·D5·D6 (ADR-016, 설정 config/valuation_v3.yaml — 값은 모두 사전값)

D2 outside_view  3년차 이후 성장률을 같은 규모 구간 기저율 중앙값 쪽으로 당긴다(Mauboussin 2016; Chan·Karceski·Lakonishok 2003)
D3 normalize     경기순환 업종은 마지막 blend_years 동안 마진을 한 사이클 평균으로 옮겨 계속가치를 정상화 이익에 둔다(Damodaran)
D5 exit_check    계속가치 ÷ 다음 해 EBIT(내포 출구 EV/EBIT)가 업종 범위를 벗어나면 경고
D6 moat_ronic    RONIC = WACC + max_spread × 해자 점수(drivers의 ronic_spread가 있으면 그것이 우선)
"""
import csv
import functools
import math
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
FUND = ROOT / "knowledge" / "models" / "fundamentals" / "us"


@functools.lru_cache(maxsize=1)
def cfg():
    return yaml.safe_load((ROOT / "config" / "valuation_v3.yaml").read_text(encoding="utf-8"))


def outside_view(growth, median, c):
    """growth 목록을 기저율 중앙값 쪽으로 혼합. median이 없거나 꺼져 있으면 그대로"""
    ov = c.get("outside_view") or {}
    if median is None or not ov.get("enabled"):
        return list(growth)
    s, k = int(ov.get("start_year", 3)), float(ov.get("k", 0.35))
    out = []
    for t, g in enumerate(growth, start=1):
        w = 0.0 if t <= s else 1 - math.exp(-k * (t - s))
        out.append((1 - w) * g + w * median)
    return out


def base_median(start_rev, sample, years=5):
    """같은 규모 구간 기저율 5년 CAGR 중앙값(표본 30개 미만이면 전체)"""
    import baserates
    lo, hi, _ = baserates.bucket_of(start_rev)
    xs = sorted(c for r, c in sample if lo <= r < hi)
    if len(xs) < 30:
        xs = sorted(c for _, c in sample)
    return xs[len(xs) // 2] if xs else None


@functools.lru_cache(maxsize=64)
def cycle_margin(ticker, years=10):
    """SEC 연간 영업이익률(10-K, 회계연도 전체) 최근 years개 평균 — 피어의 한 사이클 정상화 마진. (평균, 연도 목록) 또는 (None, [])"""
    p = FUND / f"{ticker}.csv"
    if not p.exists():
        return None, []
    d = {}
    with p.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["fp"] != "FY" or not r["form"].startswith("10-K") or r["metric"] not in ("revenue", "operating_income"):
                continue
            s, e = date.fromisoformat(r["start"]), date.fromisoformat(r["end"])
            if (e - s).days < 340:
                continue
            d.setdefault(e.year, {})[r["metric"]] = float(r["value"])
    ys = sorted(y for y, v in d.items() if v.get("revenue") and "operating_income" in v)[-years:]
    if len(ys) < max(5, years // 2):
        return None, ys
    return sum(d[y]["operating_income"] / d[y]["revenue"] for y in ys) / len(ys), ys


def normalize(margins, normal, c):
    """마지막 blend_years 동안 normal 마진으로 선형 이동"""
    if normal is None:
        return list(margins)
    n, b = len(margins), int((c.get("normalize") or {}).get("blend_years", 3))
    b = max(1, min(b, n))
    out = list(margins)
    start = out[n - b - 1] if n - b - 1 >= 0 else out[0]
    for i in range(b):
        out[n - b + i] = start + (normal - start) * (i + 1) / b
    return out


def normal_margin(spec):
    """drivers·sotp의 cyclical: {normal: x} 또는 {peer: TICKER, years: 10} → (마진, 근거 문자열)"""
    if not spec:
        return None, ""
    if spec.get("normal") is not None:
        return float(spec["normal"]), spec.get("source", "drivers 지정")
    m, ys = cycle_margin(spec["peer"], int(spec.get("years", 10)))
    if m is None:
        return None, f"{spec['peer']} SEC 연간 이익률 이력 부족"
    return m, f"{spec['peer']} SEC 10-K 영업이익률 {ys[0]}~{ys[-1]} 평균 {m:.1%}"


def moat_ronic(wacc, company, c):
    """RONIC(없으면 None = WACC). 명시 ronic_spread 우선, 다음 moat 점수"""
    if company.get("ronic_spread"):
        return wacc + company["ronic_spread"]
    moat = company.get("moat_score")
    if moat is None:
        return None
    return wacc + float((c.get("roic_fade") or {}).get("max_spread", 0.08)) * max(0.0, min(1.0, float(moat)))


def exit_check(res, d, industry, c):
    """(내포 EV/EBIT, 범위, 경고 문자열 또는 None)"""
    rows = res["rows"]
    w, g = d["wacc"], d["g_term"]
    ebit_next = rows[-1]["rev"] * (1 + g) * rows[-1]["margin"]
    if ebit_next <= 0:
        return None, None, "계속가치 해의 EBIT가 0 이하 — 출구 배수 점검 불가"
    ronic = d.get("ronic") or w
    cv = rows[-1]["nopat"] * (1 + g) * (1 - g / ronic) / (w - g)
    mult = cv / ebit_next
    rng = (c.get("exit_check") or {}).get("ranges", {})
    lo, hi = rng.get(industry) or rng.get("default", [6, 20])
    warn = None if lo <= mult <= hi else f"내포 출구 EV/EBIT {mult:.1f}배가 업종 범위 {lo}~{hi}배 밖"
    return mult, (lo, hi), warn
