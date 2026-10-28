"""M5 기대 역산(가격 내포 기대, Mauboussin·Rappaport) — 시장 가격과 같아지는 성장·마진을 푼다

성장 배율 k: gₜ' = g_end + k·(gₜ − g_end)  (장기 성장률은 고정하고 초과 성장의 크기만 바꿈)
마진 이동 δ: mₜ' = mₜ + δ
목표는 지금 지분가치(=시가총액) 또는 h년 뒤 지분가치(=k배 시가총액 — 2배·10배에 필요한 가정).
"""
import copy

import dcf


def _scaled(d, k):
    e = d["growth"][-1]
    out = copy.deepcopy(d)
    out["growth"] = [e + k * (g - e) for g in d["growth"]]
    return out


def _shifted(d, delta):
    out = copy.deepcopy(d)
    out["margin"] = [m + delta for m in d["margin"]]
    return out


def _equity(d, year):
    return dcf.value(d)["equity"] if year == 0 else dcf.equity_at(d, year)


def _solve(f, target, lo, hi, iters=80):
    flo, fhi = f(lo) - target, f(hi) - target
    if flo * fhi > 0:
        return None
    for _ in range(iters):
        mid = (lo + hi) / 2
        fm = f(mid) - target
        if (fm < 0) == (flo < 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def cagr(d, years=5):
    rev, r = d["rev0"], d["rev0"]
    for g in d["growth"][:years]:
        r *= 1 + g
    return (r / rev) ** (1 / years) - 1


def implied_growth(d, target_equity, year=0, cagr_years=5):
    """(배율 k, 내포 매출 CAGR) — 풀 수 없으면 (None, None)"""
    k = _solve(lambda x: _equity(_scaled(d, x), year), target_equity, -3.0, 12.0)
    if k is None:
        return None, None
    return k, cagr(_scaled(d, k), cagr_years)


def implied_margin_shift(d, target_equity, year=0):
    return _solve(lambda x: _equity(_shifted(d, x), year), target_equity, -0.5, 0.5)
