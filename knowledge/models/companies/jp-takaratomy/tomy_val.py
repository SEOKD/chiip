"""타카라토미(7867) 밸류에이션 — DCF(맥킨지식 성장 감속·이익률 수렴·재투자) + 역DCF + 몬테카를로 + 배수 사다리.
금액 단위: 십억 엔(B¥). 기준일 2026-10-30 종가."""
import json, math, random, statistics

P = 4922.0                       # 10/30 종가(엔)
SH = 0.086165                    # 기본 주식 수(십억 주) = 발행 93,616,650 − 자기주식 7,451,766 (2026-06-30)
MCAP = P * SH                    # B¥
CASH, DEBT = 38.628, 5.798       # 2026-06-30 현금·단기투자, 총차입(리스 포함 근사)
NET_CASH = CASH - DEBT
EV = MCAP - NET_CASH
TAX = 0.306                      # 일본 법정 실효세율 근사
RF, ERP, CRP, BETA = 0.02758, 0.042, 0.0091, 1.0
WACC = RF + BETA * (ERP + CRP)   # 무차입에 가까워 자기자본비용 ≈ WACC
G_T = 0.02
REV0 = 300.0                     # FY3/2027 회사 가이던스(10/29 상향)
H = 10


def dcf(g1, decay, m0, mt, s2c, wacc=WACC, gt=G_T, yrs_to_target=4, ret=False):
    rev, g, m = REV0, g1, m0
    pv, fcfs = 0.0, []
    for t in range(1, H + 1):
        prev = rev
        g = g1 if t == 1 else gt + (g - gt) * decay
        rev = prev * (1 + g)
        m = mt if t >= yrs_to_target else m0 + (mt - m0) * t / yrs_to_target
        nopat = rev * m * (1 - TAX)
        reinv = (rev - prev) / s2c
        fcf = nopat - reinv
        fcfs.append(fcf)
        pv += fcf / (1 + wacc) ** (t - 0.5)
    nopat_t1 = rev * (1 + gt) * mt * (1 - TAX)
    ronic = wacc  # 계속가치: 성장의 가치 창출 없음(맥킨지 기본)
    tv = nopat_t1 * (1 - gt / ronic) / (wacc - gt)
    pv_tv = tv / (1 + wacc) ** (H - 0.5)
    equity = pv + pv_tv + NET_CASH
    if ret:
        return equity, pv_tv / (pv + pv_tv), fcfs
    return equity


SC = {
    "bear": dict(g1=0.00, decay=0.6, m0=0.09, mt=0.085, s2c=3.0, prob=0.30,
                 why="FY27 상반기 쏠림·관세 환급 일회성이 빠지고 베이블레이드 X 사이클이 꺾임 → 매출 정체, OPM 8.5%"),
    "base": dict(g1=0.05, decay=0.7, m0=0.10, mt=0.105, s2c=3.0, prob=0.50,
                 why="Kidults·아시아가 정형 성장 5%대를 지키고 OPM 10~10.5% 유지"),
    "bull": dict(g1=0.10, decay=0.8, m0=0.105, mt=0.13, s2c=3.0, prob=0.20,
                 why="북미·중국 현지화와 새 IP(카드게임·캐릭터)가 겹쳐 두 자릿수 성장, OPM 13%로 반다이남코 쪽 체질 접근"),
}

out = {"mcap": MCAP, "ev": EV, "net_cash": NET_CASH, "wacc": WACC, "scen": {}}
for k, s in SC.items():
    eq, tvshare, _ = dcf(s["g1"], s["decay"], s["m0"], s["mt"], s["s2c"], ret=True)
    out["scen"][k] = {"equity": eq, "x": eq / MCAP, "per_share": eq / SH, "tv_share": tvshare, "prob": s["prob"], "why": s["why"]}
out["prob_weighted_x"] = sum(v["x"] * v["prob"] for v in out["scen"].values())

# 역DCF: 기본 이익률 경로(OPM 10%→10.5%) 고정, 1년차 성장 g1을 풀어 시가총액과 같게 → 5년 매출 CAGR
lo, hi = -0.1, 0.6
for _ in range(80):
    mid = (lo + hi) / 2
    if dcf(mid, 0.7, 0.10, 0.105, 3.0) < MCAP:
        lo = mid
    else:
        hi = mid
g_imp = (lo + hi) / 2
r, g = REV0, g_imp
revs = []
for t in range(1, 6):
    g = g_imp if t == 1 else G_T + (g - G_T) * 0.7
    r *= 1 + g
    revs.append(r)
out["implied_g1"] = g_imp
out["implied_5y_cagr"] = (revs[-1] / REV0) ** (1 / 5) - 1
out["implied_rev_y5"] = revs[-1]
# 같은 질문을 이익률로: 성장은 기본(5% 감속) 고정, 장기 OPM을 풀어라
lo, hi = 0.0, 0.4
for _ in range(80):
    mid = (lo + hi) / 2
    if dcf(0.05, 0.7, 0.10, mid, 3.0) < MCAP:
        lo = mid
    else:
        hi = mid
out["implied_opm"] = (lo + hi) / 2

# 민감도: WACC × 영구성장(기본 시나리오, 배)
out["sens"] = {f"{w:.3f}": {f"{gt:.3f}": dcf(0.05, 0.7, 0.10, 0.105, 3.0, wacc=w, gt=gt) / MCAP
                            for gt in (0.01, 0.015, 0.02, 0.025)} for w in (0.07, 0.075, WACC, 0.085, 0.09)}

# 몬테카를로(5년 보유): 매출 CAGR·5년차 OPM·출구 P/E·누적 주주환원
random.seed(7)
N = 20000
mult = []
NI_MARGIN_RATIO = 20.0 / 30.0     # 순이익/영업이익 (FY27 가이던스 200/300)
for _ in range(N):
    cagr = random.gauss(0.05, 0.05)
    opm = max(0.04, random.gauss(0.105, 0.02))
    pe = math.exp(random.gauss(math.log(19.0), 0.25))
    rev5 = REV0 * (1 + cagr) ** 4             # FY27 → FY31
    ni5 = rev5 * opm * NI_MARGIN_RATIO
    shrink = (1 - 0.012) ** 5                  # 자사주 매입 연 1.2% 주식 수 감소(총환원 50% 중 일부, 추정)
    eq5 = ni5 * pe
    div = 5 * 0.015                            # 배당 수익률 1.5% × 5년(단순 합)
    mult.append(eq5 / MCAP / shrink + div)
mult.sort()
q = lambda p: mult[int(p * (N - 1))]
out["mc"] = {"p10": q(0.10), "p50": q(0.50), "p90": q(0.90),
             "p_ge1": sum(m >= 1 for m in mult) / N, "p_ge2": sum(m >= 2 for m in mult) / N,
             "p_ge3": sum(m >= 3 for m in mult) / N, "p_ge5": sum(m >= 5 for m in mult) / N, "p_ge10": sum(m >= 10 for m in mult) / N}

# 배수 사다리: 출구 Fwd P/E 20배, 순이익률 6.7%(FY27 가이던스) / OPM 10% → 필요 매출·CAGR(FY27 기준 5년)
lad = []
for k in (2, 3, 5, 10):
    cap = MCAP * k
    ni = cap / 20.0
    rev = ni / (20.0 / 300.0)
    eps = ni / SH
    lad.append({"k": k, "mcap": cap, "ni": ni, "rev": rev, "rev_cagr5": (rev / REV0) ** 0.2 - 1,
                "eps": eps, "eps_cagr5": (eps / 231.29) ** 0.2 - 1, "opm": 0.10,
                "rev_at_13pct": ni / (300 * 0.13 * (20 / 30) / 300) if False else ni / (0.13 * NI_MARGIN_RATIO),
                })
for d in lad:
    d["rev_cagr5_at13"] = (d["rev_at_13pct"] / REV0) ** 0.2 - 1
out["ladder"] = lad

# 멀티플
peers = {"반다이남코": 6211 / 250.28, "산리오": 1254 / 54.31, "해피넷": 6100 / 384.75,
         "해즈브로": 119.09 / 7.113, "마텔": 15.42 / 1.294, "스핀마스터": 20.44 / 1.988}
out["pe_fwd_guid"] = P / 231.29
out["pe_fwd_cons"] = P / 239.075
out["pe_ttm"] = P / 140.03
out["peers_pe"] = peers
out["peer_median"] = statistics.median(peers.values())
out["jp_peer_median"] = statistics.median([peers["반다이남코"], peers["산리오"], peers["해피넷"]])
out["ev_ebitda_ttm"] = EV / 34.652
print(json.dumps(out, ensure_ascii=False, indent=1, default=lambda x: round(x, 4)))
