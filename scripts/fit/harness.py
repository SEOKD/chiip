"""피팅 하네스 (BUILD_PROMPT §21.14, ADR-010 §3) — 시간 순 롤링 검증·사전값 축소·채택 관문

원칙
- 미래 정보 누설 금지: 학습 구간은 항상 검증 구간보다 앞선다(walk-forward).
- 작은 표본은 사전값(논문·관행) 쪽으로 당긴다: shrink(추정, 사전, n, k) = (n·추정 + k·사전) / (n + k).
- 채택은 표본 외 손실이 사전값보다 충분히 줄 때만(registry.yaml adoption). 매일 다시 맞추지 않는다.
모델 몫: 무엇을 피팅할지(가설·논문 근거)와 결과 해석. 이 파일은 숫자만 다룬다(표준 라이브러리만 사용).
"""
import math


def walk_forward(n, min_train, step=1, horizon=1):
    """(학습 끝 인덱스(배타), 검증 인덱스 목록) — 학습은 [0, t), 검증은 [t, t+horizon)"""
    t = min_train
    while t + horizon <= n:
        yield t, list(range(t, t + horizon))
        t += step


def shrink(estimate, prior, n, k):
    if estimate is None or (isinstance(estimate, float) and math.isnan(estimate)):
        return prior
    if prior is None:
        return estimate
    return (n * estimate + k * prior) / (n + k)


def mse(pred, actual):
    pairs = [(p, a) for p, a in zip(pred, actual) if p is not None and a is not None]
    return sum((p - a) ** 2 for p, a in pairs) / len(pairs) if pairs else None


def ols(x, y):
    """단순 회귀 (기울기, 절편). 표본 2개 미만이거나 x 분산 0이면 None"""
    pts = [(a, b) for a, b in zip(x, y) if a is not None and b is not None]
    if len(pts) < 2:
        return None
    mx = sum(a for a, _ in pts) / len(pts)
    my = sum(b for _, b in pts) / len(pts)
    sxx = sum((a - mx) ** 2 for a, _ in pts)
    if sxx == 0:
        return None
    slope = sum((a - mx) * (b - my) for a, b in pts) / sxx
    return slope, my - slope * mx


def evaluate(series, fit_fn, predict_fn, prior, k, min_train, step=1, horizon=1, loss=mse):
    """시간 순 데이터 series(관측 목록)에 대해
    fit_fn(train) → 추정값, predict_fn(param, test) → (예측 목록, 실제 목록).
    사전값 고정 예측과 축소 피팅 예측의 표본 외 손실을 비교한다."""
    pp, pa, fp, fa, last = [], [], [], [], prior
    for t, idx in walk_forward(len(series), min_train, step, horizon):
        train, test = series[:t], [series[i] for i in idx]
        est = fit_fn(train)
        last = shrink(est, prior, len(train), k)
        p1, a1 = predict_fn(prior, test)
        p2, a2 = predict_fn(last, test)
        pp += p1; pa += a1; fp += p2; fa += a2
    return {"param": last, "oos_prior": loss(pp, pa), "oos_fit": loss(fp, fa), "n_oos": len(fa)}


def adoption_decision(oos_prior, oos_fit, n_oos, rule):
    if oos_prior is None or oos_fit is None:
        return False, "표본 외 손실 계산 불가"
    if n_oos < int(rule.get("min_oos_n", 30)):
        return False, f"표본 외 관측 {n_oos} < {rule.get('min_oos_n', 30)}"
    if oos_prior == 0:
        return False, "사전값 손실 0 — 개선 여지 없음"
    gain = (oos_prior - oos_fit) / oos_prior
    need = float(rule.get("min_oos_improvement", 0.05))
    if gain < need:
        return False, f"표본 외 개선 {gain:.1%} < {need:.0%}"
    return True, f"표본 외 개선 {gain:.1%} (n={n_oos})"


def nested_test(base_losses, ext_losses, trials=1, alpha=0.05, min_gain=0.05):
    """기존 모델 vs 기존+파라미터 1개의 표본 외 손실 비교(같은 관측끼리 짝) — 단계적 파라미터 추가 관문(scripts/fit/stepwise.py).
    짝지은 손실 차 d = 기존 − 확장의 t 통계(Diebold & Mariano 1995, JBES — 1기 앞 예측이라 HAC 생략)를
    다중 검정 보정 문턱과 비교한다: 모델에 지금까지 시도한 파라미터 수(trials)로 본페로니 보정(Harvey, Liu & Zhu 2016, RFS — 데이터 스누핑).
    반환 (통과 여부, 이유, {"gain","t","hurdle","n"})"""
    from statistics import NormalDist
    pairs = [(b, e) for b, e in zip(base_losses, ext_losses) if b is not None and e is not None]
    n = len(pairs)
    hurdle = max(1.96, NormalDist().inv_cdf(1 - alpha / (2 * max(1, trials))))
    if n < 3:
        return False, f"짝지은 표본 외 관측 {n} < 3", {"gain": None, "t": None, "hurdle": round(hurdle, 2), "n": n}
    d = [b - e for b, e in pairs]
    mb = sum(b for b, _ in pairs) / n
    md = sum(d) / n
    sd = math.sqrt(sum((x - md) ** 2 for x in d) / (n - 1))
    t = md / (sd / math.sqrt(n)) if sd > 0 else (math.inf if md > 0 else 0.0)
    gain = md / mb if mb else None
    st = {"gain": None if gain is None else round(gain, 4), "t": round(t, 2) if math.isfinite(t) else t, "hurdle": round(hurdle, 2), "n": n}
    if gain is None or gain < min_gain:
        return False, f"표본 외 개선 {0 if gain is None else gain:.1%} < {min_gain:.0%}", st
    if t < hurdle:
        return False, f"t {t:.2f} < 보정 문턱 {hurdle:.2f}(누적 시도 {trials})", st
    return True, f"개선 {gain:.1%}, t {t:.2f} ≥ {hurdle:.2f}(누적 시도 {trials}, n={n})", st


def brier(probs, outcomes):
    pairs = [(float(p), float(o)) for p, o in zip(probs, outcomes) if p not in (None, "") and o not in (None, "")]
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs) if pairs else None


def calibration(probs, outcomes, bins=5):
    """[(구간 하한, 구간 상한, 평균 확률, 실제 적중률, n)] — 판단 보정(과신·과소신) 확인용"""
    rows = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(float(p), float(o)) for p, o in zip(probs, outcomes)
               if p not in (None, "") and o not in (None, "") and (lo <= float(p) < hi or (b == bins - 1 and float(p) == 1.0))]
        if sel:
            rows.append((lo, hi, sum(p for p, _ in sel) / len(sel), sum(o for _, o in sel) / len(sel), len(sel)))
    return rows
