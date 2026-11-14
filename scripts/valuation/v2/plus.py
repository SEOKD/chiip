"""DCF 보강 D2·D3·D5·D6 (ADR-016, 설정 config/valuation_v3.yaml — 값은 모두 사전값)

D2 outside_view  3년차 이후 성장률을 같은 규모 구간 기저율 중앙값 쪽으로 당긴다(Mauboussin 2016; Chan·Karceski·Lakonishok 2003)
D3 normalize     경기순환 업종은 마지막 blend_years 동안 마진을 한 사이클 평균으로 옮겨 계속가치를 정상화 이익에 둔다(Damodaran)
D5 exit_check    계속가치 ÷ 다음 해 EBIT(내포 출구 EV/EBIT)가 업종의 지금 EV/EBIT(Damodaran 2026-01, 성장 기대 포함)를 넘으면 '공격적' 경고.
                 아래쪽 기준은 성장이 가치를 더하지 않는 바닥 (1 − t)/WACC — RONIC ≥ WACC면 그 밑으로 갈 수 없다(ADR-040)
D6 moat_ronic    RONIC = WACC + max_spread × 해자 점수(drivers의 ronic_spread가 있으면 그것이 우선). 해자 점수는 리포트 해자 판정
                 (datapack moat.items, 근거 있는 항목만)을 멀티플 선정과 같은 점수표로 매긴다(moat_score, ADR-040). 해자에서 온 RONIC은
                 10년차 ROIC를 넘지 않는다(dcf.effective_ronic — 기존 자본으로 자본비용도 못 버는 회사가 새 투자에서만 높게 벌 수는 없다)
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


@functools.lru_cache(maxsize=1)
def _subs():
    """감시 목록 id → 업종(sub) — config/valuation.yaml universe + config/earnings_watch.yaml extra"""
    out = {}
    for f in ("valuation.yaml", "earnings_watch.yaml"):
        p = ROOT / "config" / f
        d = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
        for u in ((d or {}).get("universe") or []) + ((d or {}).get("extra") or []):
            if u.get("id") and u.get("sub"):
                out.setdefault(u["id"], u["sub"])
    return out


def cyclical_spec(company, c=None):
    """drivers의 cyclical이 우선. 없으면 감시 목록 업종이 normalize.peers에 있으면 {peer, years}(2026-11-13 SK하이닉스 점검 —
    메모리 동인에 cyclical이 없어 D3 정상화가 한 번도 켜지지 않았고, 영업이익률 80%가 10년 내내 2%p 잡음으로만 흔들렸다)"""
    if company.get("cyclical"):
        return company["cyclical"]
    nc = ((c or cfg()).get("normalize") or {})
    peer = (nc.get("peers") or {}).get(_subs().get(company.get("id")))
    return {"peer": peer, "years": int(nc.get("cycle_years", 10)), "auto": True} if peer else None


@functools.lru_cache(maxsize=64)
def cycle_sigma(ticker, window=3, years=10):
    """피어 SEC 연간 영업이익률의 window년 이동평균 표준편차 — 몬테카를로 마진 수준 충격(경로 전체에 한 번 더하는 값이라
    1년 값의 표준편차가 아니라 여러 해 평균의 흔들림을 쓴다). 이력이 부족하면 None"""
    _, ys = cycle_margin(ticker, years)
    if len(ys) < window + 2:
        return None
    p = FUND / f"{ticker}.csv"
    d = {}
    with p.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            if r["fp"] != "FY" or not r["form"].startswith("10-K") or r["metric"] not in ("revenue", "operating_income"):
                continue
            s, e = date.fromisoformat(r["start"]), date.fromisoformat(r["end"])
            if (e - s).days >= 340:
                d.setdefault(e.year, {})[r["metric"]] = float(r["value"])
    m = [d[y]["operating_income"] / d[y]["revenue"] for y in ys]
    roll = [sum(m[i:i + window]) / window for i in range(len(m) - window + 1)]
    mu = sum(roll) / len(roll)
    return math.sqrt(sum((x - mu) ** 2 for x in roll) / len(roll))


def margin_sigma(company, base, c=None):
    """경기순환 종목이면 max(동인 σ, 피어 이동평균 σ) — 아니면 동인 σ 그대로"""
    spec = cyclical_spec(company, c)
    if not spec or not spec.get("peer"):
        return base
    nc = ((c or cfg()).get("normalize") or {})
    s = cycle_sigma(spec["peer"], int(nc.get("sigma_window", 3)), int(spec.get("years", 10)))
    return max(base, s) if s else base


VERDICT_ALIAS = {"중간": "보통", "약점": "약함", "약화 중": "약함"}   # 같은 뜻 다른 표기(11/15 점검: 10건이 점수표에 없어 0점) — 멀티플 선정과 공용
SKIP_VERDICT = {"미확인", "해당 없음", None, ""}


def verdict(x):
    v = (x or {}).get("verdict")
    return VERDICT_ALIAS.get(v, v)


@functools.lru_cache(maxsize=1)
def _moat_table():
    """멀티플 선정과 같은 해자 점수표(config/tenbagger.yaml multiple_select.moat_points·moat_cap) — 두 곳이 다른 점수를 쓰지 않게 한 곳에서 읽는다"""
    t = yaml.safe_load((ROOT / "config" / "tenbagger.yaml").read_text(encoding="utf-8")) or {}
    ms = t.get("multiple_select") or {}
    return dict(ms.get("moat_points") or {}), float(ms.get("moat_cap") or 0.12)


def moat_score(dp, table=None):
    """리포트 해자 판정 → 해자 점수 0~1과 근거. 근거(evidence)가 있고 판정이 확인된 항목만 센다.
    점수 = clip(Σ 판정 점수 ÷ 상한, 0, 1) — 강함 3개면 1(넓은 해자), 강함 1·보통 2개면 0.58, 보통 2개면 0.25(멀티플 선정 해자 프리미엄과 같은 비율)"""
    pts, cap = table or _moat_table()
    used = [x for x in (((dp or {}).get("moat") or {}).get("items") or []) if verdict(x) not in SKIP_VERDICT and str(x.get("evidence") or "").strip()]
    raw = sum(pts.get(verdict(x), 0.0) for x in used)
    score = max(0.0, min(1.0, raw / cap)) if cap > 0 else 0.0
    label = "넓은 해자" if score >= 2 / 3 else "좁은 해자" if score >= 1 / 3 else "약한 해자" if score > 0 else "해자 근거 없음"
    return {"score": round(score, 3), "label": label, "n": len(used),
            "items": [f"{str(x.get('kind'))[:24]} {verdict(x)}" for x in used]}


def moat_ronic(wacc, company, c):
    """RONIC(없으면 None = WACC). 명시 ronic_spread 우선, 다음 moat 점수"""
    if company.get("ronic_spread"):
        return wacc + company["ronic_spread"]
    moat = company.get("moat_score")
    if moat is None:
        return None
    return wacc + float((c.get("roic_fade") or {}).get("max_spread", 0.08)) * max(0.0, min(1.0, float(moat)))


def exit_check(res, d, industry, c):
    """(내포 EV/EBIT, (바닥, 업종 지금 배수), 경고 문자열 또는 None).
    바닥 = (1 − t)/WACC(성장이 가치를 더하지 않을 때). 위 기준 = 업종의 지금 EV/EBIT(Damodaran, 성장 기대 포함) — 10년 뒤 안정 성장 해의
    출구 배수가 지금 업종 배수보다 높으면 계속가치를 공격적으로 잡은 것이다. 낮은 것은 보수 가정의 결과라 경고하지 않는다(ADR-040:
    옛 범위 '8~25배' 등은 대조 전 어림값이라 122종목 중 71곳이 '범위 밖'으로 떴다)"""
    import dcf
    rows = res["rows"]
    w, g = d["wacc"], d["g_term"]
    ebit_next = rows[-1]["rev"] * (1 + g) * rows[-1]["margin"]
    if ebit_next <= 0:
        return None, None, "계속가치 해의 EBIT가 0 이하 — 출구 배수 점검 불가"
    ronic = dcf.effective_ronic(d, rows)
    cv = rows[-1]["nopat"] * (1 + g) * (1 - g / ronic) / (w - g)
    mult = cv / ebit_next
    ec = c.get("exit_check") or {}
    ind = (ec.get("industry_ev_ebit") or {}).get(industry, ec.get("default_ev_ebit"))
    tax = d.get("tax")
    if tax is None:   # 세율이 없으면 마지막 해 NOPAT ÷ EBIT로 되짚는다
        tax = 1 - rows[-1]["nopat"] / (rows[-1]["rev"] * rows[-1]["margin"])
    floor = (1 - tax) / w
    warn = f"내포 출구 EV/EBIT {mult:.1f}배가 업종 지금 배수 {ind:.1f}배보다 높다 — 계속가치가 공격적" if ind and mult > ind else None
    return mult, (round(floor, 1), ind), warn
