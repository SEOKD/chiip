"""M8 의사결정 보조 3요인 (마스터 지시 2026-10-28) — 매수 매력 · 위험 예산 지표 · 상방

몬테카를로 추출(지금 가치 v0, h년 뒤 가치 vh — 둘 다 지분가치 절대값)과 시가총액·자기자본비용으로 계산한다.
가정: h년 뒤 시장가격이 그때의 내재가치로 수렴(가치 수렴 가정), 그 사이 배당 없음(FCFF는 순차입 상환).
① 매수 매력: 연 기대수익 = (E[vh]/시총)^(1/h) − 1, 자기자본비용 대비 초과분, 연수익 > 자기자본비용 확률, 안전마진 = P10(v0)/시총
② 위험 예산 지표: 기대 초과수익(자기자본비용 대비)이 기준 미만이면 0. 그 외에는 추출 분포에서 E[log((1−f)(1+rf)^h + f·vh/시총)]를 최대화하는 켈리 비율 f*(0~1, 차입·공매도 없음)의
   일부(기본 1/4 — 추정 오차 대비, MacLean·Thorp·Ziemba 분수 켈리 관행) + 비중 상한. 하방: h년 하위 10% 손실, 30% 이상 손실 확률, 연수익 변동성
③ 상방: E[vh]/시총, P(≥2·3·10배), P90(vh)/시총
치입은 투자자문 자격이 없다 — 출력은 판단을 돕는 지표이며 매수·매도 지시나 금액 결정이 아니다.
"""
import math
import statistics

import montecarlo


def annualized(ratio, h):
    return ratio ** (1 / h) - 1 if ratio > 0 else -1.0


def kelly(ratios, rf, h, steps=100):
    """ratios = vh/시총 추출값. (f*, 기대 로그 성장)"""
    base = (1 + rf) ** h
    best_f, best_g = 0.0, -math.inf
    for i in range(steps + 1):
        f = i / steps
        g = sum(math.log(max(1e-12, (1 - f) * base + f * x)) for x in ratios) / len(ratios)
        if g > best_g + 1e-12:
            best_f, best_g = f, g
    return best_f, best_g


def signal(excess, p_beat, mos, c):
    if excess >= c["strong_excess"] and p_beat >= c["strong_p_beat"] and mos >= c["strong_mos"]:
        return "강함"
    if excess >= c["neutral_excess"] and p_beat >= c["neutral_p_beat"]:
        return "중립"
    return "약함"


def compute(mc, mcap, ke, rf, c, h=5):
    """mc: montecarlo.simulate 결과, c: config/valuation_v2.yaml decision 블록"""
    vh = [v / mcap for v in mc["vh"]]
    v0 = [v / mcap for v in mc["v0"]]
    if not vh:
        return None
    ann = [annualized(x, h) for x in vh]
    exp_ret = annualized(sum(vh) / len(vh), h)
    excess = exp_ret - ke
    p_beat = sum(1 for r in ann if r > ke) / len(ann)
    mos = montecarlo.quantile(v0, 0.10)
    f_star, _ = kelly(vh, rf, h)
    # 켈리는 무위험금리 대비라 주식 위험 보상(자기자본비용)을 반영하지 못한다 → 기대 초과수익이 기준 미만이면 위험 예산 0
    gated = excess < c["neutral_excess"]
    budget = 0.0 if gated else min(c["max_position"], c["kelly_fraction"] * f_star)
    return {
        "horizon": h,
        "attractiveness": {"exp_return": exp_ret, "median_return": annualized(montecarlo.quantile(vh, 0.5), h),
                           "ke": ke, "excess": excess, "p_beat_ke": p_beat, "margin_of_safety": mos,
                           "signal": signal(excess, p_beat, mos, c)},
        "risk_budget": {"kelly_full": f_star, "kelly_fraction": c["kelly_fraction"], "budget": budget, "cap": c["max_position"], "gated": gated,
                        "p10_loss": montecarlo.quantile(vh, 0.10) - 1, "p_loss_30": sum(1 for x in vh if x < 0.7) / len(vh),
                        "vol_annual": statistics.pstdev(ann) if len(ann) > 1 else None},
        "upside": {"exp_multiple": sum(vh) / len(vh), "p2": sum(1 for x in vh if x >= 2) / len(vh),
                   "p3": sum(1 for x in vh if x >= 3) / len(vh), "p10": sum(1 for x in vh if x >= 10) / len(vh),
                   "p90_multiple": montecarlo.quantile(vh, 0.90)},
    }


def lines(d):
    """텔레그램·카드용 3줄 — 지표·확률로만(권유 문구 없음)"""
    a, r, u = d["attractiveness"], d["risk_budget"], d["upside"]
    h = d["horizon"]
    return [
        f"① 매수 매력: 연 기대수익 {a['exp_return']:+.1%} (자기자본비용 {a['ke']:.1%} 대비 {a['excess']:+.1%}p) · 자본비용 초과 확률 {a['p_beat_ke']:.0%} · 안전마진 {a['margin_of_safety']:.2f} → 정량 신호 {a['signal']}",
        (f"② 위험 예산 지표(이론): 0% — 기대수익이 자기자본비용에 못 미침(무위험 대비 켈리 {r['kelly_full']:.0%}는 참고) · {h}년 하위10% {r['p10_loss']:+.0%} · 30%+ 손실 확률 {r['p_loss_30']:.0%}"
         if r.get("gated") else
         f"② 위험 예산 지표(이론): 1/{round(1 / r['kelly_fraction'])} 켈리 {r['budget']:.1%} (상한 {r['cap']:.0%}) · {h}년 하위10% {r['p10_loss']:+.0%} · 30%+ 손실 확률 {r['p_loss_30']:.0%}"),
        f"③ 상방({h}년): 기대 {u['exp_multiple']:.2f}배 · 2배 {u['p2']:.0%} · 3배 {u['p3']:.0%} · 10배 {u['p10']:.0%} · 상위10% {u['p90_multiple']:.2f}배",
    ]
