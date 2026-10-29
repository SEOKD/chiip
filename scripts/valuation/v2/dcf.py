"""M3 가치 엔진 — 기업 DCF(FCFF) + 가치 동인 계속가치 + 경제적 이익 항등 + 지분 브리지 + 금리 민감도

drivers(dict, 금액 단위는 종목 drivers.yaml이 정한 하나로 통일 — 예: 10억 달러):
  rev0        기준연도 매출
  growth      [g1..gN]  연도별 매출 성장률
  margin      [m1..mN]  연도별 영업(EBITA) 마진
  tax         영업세율
  s2c         증분 매출 ÷ 증분 투하자본(재투자 효율). 재투자ₜ = (매출ₜ − 매출ₜ₋₁) / s2c
  ic0         기준연도 말 투하자본
  wacc, g_term, ronic(없으면 = wacc)
  net_debt, shares, nonop(비영업자산, 선택), minority(소수지분 등 부채성, 선택)
계속가치 = NOPAT_{N+1} × (1 − g/RONIC) / (WACC − g)  (McKinsey 핵심 가치 동인 공식)
"""
import copy


def path_linear(start, end, n):
    if n == 1:
        return [end]
    return [start + (end - start) * i / (n - 1) for i in range(n)]


def margin_path(m0, target, year_target, n, lr=None, lam=0.0):
    """m0 → target(연도 year_target까지 선형) → 이후 장기 마진 lr로 연 lam 비율씩 수렴(Fama·French형 페이드)"""
    out = []
    for t in range(1, n + 1):
        if t <= year_target:
            out.append(m0 + (target - m0) * t / year_target)
        else:
            prev = out[-1]
            out.append(prev if lr is None else lr + (prev - lr) * (1 - lam))
    return out


def project(d):
    rows, rev, ic = [], d["rev0"], d["ic0"]
    for t, (g, m) in enumerate(zip(d["growth"], d["margin"]), start=1):
        new = rev * (1 + g)
        reinv = (new - rev) / d["s2c"]
        nopat = new * m * (1 - d["tax"])
        rows.append({"t": t, "rev": new, "margin": m, "nopat": nopat, "reinv": reinv, "fcff": nopat - reinv,
                     "ic_open": ic, "roic": nopat / ic if ic > 0 else None})
        ic += reinv
        rev = new
    return rows, ic


def value(d, midyear=None):
    """midyear: None이면 d['midyear'](기본 False). McKinsey 관행은 현금흐름이 연중 고르게 발생한다고 보고 EV × (1+WACC)^0.5"""
    midyear = d.get("midyear", False) if midyear is None else midyear
    rows, ic_T = project(d)
    w, g = d["wacc"], d["g_term"]
    ronic = d.get("ronic") or w
    if w <= g:
        raise ValueError("WACC가 영구성장률보다 커야 한다")
    n = len(rows)
    pv = [r["fcff"] / (1 + w) ** r["t"] for r in rows]
    nopat_next = rows[-1]["nopat"] * (1 + g)
    cv = nopat_next * (1 - g / ronic) / (w - g)
    pv_cv = cv / (1 + w) ** n
    ev = sum(pv) + pv_cv
    # 경제적 이익 항등 검증(같은 연말 할인)
    ep_pv = sum((r["nopat"] - w * r["ic_open"]) / (1 + w) ** r["t"] for r in rows)
    ep_next = nopat_next - w * ic_T
    cv_ep = ep_next / w + nopat_next * (g / ronic) * (ronic - w) / (w * (w - g))
    ev_ep = d["ic0"] + ep_pv + cv_ep / (1 + w) ** n
    adj = (1 + w) ** 0.5 if midyear else 1.0
    ev *= adj
    eq = ev - d["net_debt"] + d.get("nonop", 0.0) - d.get("minority", 0.0)
    return {"ev": ev, "equity": eq, "per_share": eq / d["shares"], "cv_share": pv_cv * adj / ev if ev else None,
            "ev_ep": ev_ep * adj, "ep_gap": abs(ev_ep * adj - ev) / abs(ev) if ev else None, "rows": rows}


def equity_at(d, year, midyear=None):
    """year년 뒤 시점의 내재 지분가치(그때까지의 FCFF는 순차입 상환에 쓴다고 가정 — 배당·자사주 없음).
    순현금에는 세후 이자 kd, 모자라는 돈(순차입)에는 자본비용 WACC를 붙인다 — 적자 램프를 싼 차입으로 메운다고 두면 레버리지 효과로
    5년 뒤 지분가치가 자본비용보다 빨리 커지는 착시가 생긴다(2026-10-29 CBRS 점검: 이자 없이 FCFF만 더해 '5년 뒤' 배수가 부풀었다)"""
    rows, _ = project(d)
    w, kd = d["wacc"], d.get("kd", 0.0)
    nd = d["net_debt"]
    for r in rows[:year]:
        nd = nd * (1 + (kd if nd < 0 else w)) - r["fcff"]
    later = copy.deepcopy(d)
    later["rev0"] = rows[year - 1]["rev"]
    later["growth"] = d["growth"][year:]
    later["margin"] = d["margin"][year:]
    later["ic0"] = d["ic0"] + sum(r["reinv"] for r in rows[:year])
    later["net_debt"] = nd
    if not later["growth"]:   # 명시 기간 끝 → 계속가치만
        g = d["g_term"]
        ronic = d.get("ronic") or w
        nopat_next = rows[-1]["nopat"] * (1 + g)
        ev = nopat_next * (1 - g / ronic) / (w - g)
        return ev - nd + d.get("nonop", 0.0) - d.get("minority", 0.0)
    return value(later, midyear)["equity"]


def rate_sensitivity(d, bp=50):
    """할인율 +bp일 때 주당가치 변화율과 근사 듀레이션"""
    base = value(d)["per_share"]
    up = copy.deepcopy(d)
    up["wacc"] += bp / 10000
    v = value(up)["per_share"]
    chg = v / base - 1
    return {"chg": chg, "duration": -chg / (bp / 10000)}
