"""P·Q 전망 엔진 (마스터 지시 2026-11-08 "10년 P·Q 사이클에서 P 전망, Q 전망이 전문 모델링을 바탕으로 합리적으로 추정되고 있는지 점검하고
부족한 부분이 있다면 전문 기술 바탕으로 체계적으로 바꿔라")

점검에서 드러난 결함과 고친 방법:
  ① 컨센서스를 쓰지 않았다 — AR(2) 통계 외삽만이라 NVDA처럼 다음 4분기 매출 컨센서스가 +60% 늘어도 물량 갭이 4분기 만에 −로 돌았다.
     → 매출 = P × Q 항등식으로 컨센서스 매출 경로에서 가격 전망을 빼 '컨센서스 내포 Q'를 만든다(가격·물량 브리지, price-volume bridge).
     통계 Q와 컨센서스 내포 Q를 분산 역수 가중으로 합친다(Bates & Granger 1969 예측 결합). 애널리스트 예측이 시계열보다 앞선다는
     실증(Brown, Hagerman, Griffin & Zmijewski 1987)대로 가까운 분기는 컨센서스 쪽 무게가 크고, 멀수록 통계 쪽으로 옮겨 간다.
  ② HP 필터 끝점 편향 — 두 방향 필터는 마지막 점의 추세를 최근 값 쪽으로 끌어 현재 갭을 작게 본다.
     → 전망 경로를 이어 붙인 뒤 필터를 다시 건다(forecast extension: Kaiser & Maravall 1999, Mise·Kim·Newbold 2005).
  ③ AR 차수 고정·정상성 미점검 — AR(2) 계수가 단위근 근처(모듈러스 0.94)여도 그대로 썼다.
     → 절편 없는 AR(p), p = 1~3을 BIC(Schwarz 1978)로 고르고, 동반 행렬 최대 고윳값이 max_root를 넘으면 계수를 줄여 정상성을 지킨다.
  ④ 불확실성이 없었다 → ψ 가중치로 h분기 예측 표준오차, 80% 범위를 낸다(Box & Jenkins).
상수는 config/pq_cycle.yaml forecast, 등록부 prm-pq-fc-*. 전망은 모형 산출이며 가이던스가 아니다.
"""
import math

Z80 = 1.2816


def _solve(A, b):
    """작은 정규방정식 — 가우스 소거. 특이하면 None"""
    n = len(b)
    A = [list(r) for r in A]
    b = list(b)
    for i in range(n):
        p = max(range(i, n), key=lambda r: abs(A[r][i]))
        A[i], A[p], b[i], b[p] = A[p], A[i], b[p], b[i]
        if abs(A[i][i]) < 1e-12:
            return None
        for r in range(n):
            if r != i:
                f = A[r][i] / A[i][i]
                A[r] = [a - f * c for a, c in zip(A[r], A[i])]
                b[r] -= f * b[i]
    return [b[i] / A[i][i] for i in range(n)]


def _radius(phi):
    """AR 동반 행렬의 최대 고윳값 크기 — 거듭제곱법(p ≤ 3)"""
    p = len(phi)
    if p == 1:
        return abs(phi[0])
    if p == 2:
        d = phi[0] ** 2 + 4 * phi[1]
        if d >= 0:
            return max(abs((phi[0] + math.sqrt(d)) / 2), abs((phi[0] - math.sqrt(d)) / 2))
        return math.sqrt(-phi[1])
    v = [1.0] + [0.0] * (p - 1)
    r = 0.0
    for _ in range(400):
        w = [sum(f * x for f, x in zip(phi, v))] + v[:-1]
        n = math.sqrt(sum(x * x for x in w)) or 1e-12
        r, v = n, [x / n for x in w]
    return r


def ar_fit(y, pmax=3, intercept=False, max_root=0.95):
    """BIC로 차수를 고른 AR(p). {p, phi, c, sigma, radius, shrunk}. 표본이 모자라면 None"""
    best = None
    for p in range(1, pmax + 1):
        rows = [(([1.0] if intercept else []) + [y[t - k] for k in range(1, p + 1)], y[t]) for t in range(p, len(y))]
        k = p + (1 if intercept else 0)
        if len(rows) < max(8, 3 * k):
            continue
        A = [[sum(x[i] * x[j] for x, _ in rows) for j in range(k)] for i in range(k)]
        b = [sum(x[i] * t for x, t in rows) for i in range(k)]
        beta = _solve(A, b)
        if beta is None:
            continue
        res = [t - sum(bi * xi for bi, xi in zip(beta, x)) for x, t in rows]
        s2 = sum(e * e for e in res) / len(res)
        bic = len(res) * math.log(max(s2, 1e-12)) + k * math.log(len(res))
        if best is None or bic < best["bic"]:
            c, phi = (beta[0], beta[1:]) if intercept else (0.0, beta)
            best = {"p": p, "phi": phi, "c": c, "sigma": math.sqrt(s2 * len(res) / max(len(res) - k, 1)), "bic": bic}
    if not best:
        return None
    r = _radius(best["phi"])
    best["shrunk"] = r > max_root
    if best["shrunk"]:   # 정상성 강제 — 계수를 j차에 (max_root / r)^j씩 줄이면 모든 근이 같은 비율로 안쪽으로 들어온다
        f = max_root / r
        best["phi"] = [a * f ** (j + 1) for j, a in enumerate(best["phi"])]
        r = max_root
    best["radius"] = r
    return best


def ar_path(y, fit, n):
    """평균 경로와 h분기 표준오차(ψ 가중치)"""
    phi, c = fit["phi"], fit["c"]
    h, out = list(y), []
    for _ in range(n):
        h.append(c + sum(a * h[-1 - j] for j, a in enumerate(phi)))
        out.append(h[-1])
    psi = [1.0]
    for j in range(1, n):
        psi.append(sum(phi[k] * psi[j - 1 - k] for k in range(len(phi)) if j - 1 - k >= 0))
    se = [fit["sigma"] * math.sqrt(sum(x * x for x in psi[:i + 1])) for i in range(n)]
    return out, se


def _scale(est, last):
    """컨센서스 단위를 실적 단위로 — 마지막 실적과 가장 가까운 10의 거듭제곱 배"""
    if not est or not last:
        return 1.0
    return min((10 ** k for k in (0, 3, 6, 9, 12)), key=lambda f: abs(math.log(est * f / last)))


def consensus_quarters(dp, last_q, last_rev, shift_q, n=8):
    """마지막 실적 분기 다음 n분기의 컨센서스 분기 매출(실적 단위). {라벨: 매출, …}, 근거 문구.
    1~4분기 = consensus.quarters_est(키 순서대로 다음 분기부터 — 회계 분기 라벨이 실적 라벨과 달라도 순서로 맞춘다),
    5~8분기 = 같은 분기 전년 컨센서스 × 연간 컨센서스 성장률(consensus.rev의 이웃한 두 회계연도 중 4분기 합에 가까운 쌍)"""
    c = dp.get("consensus") or {}
    qe = c.get("quarters_est") or {}
    vals = [float(qe[k]) for k in sorted(qe) if qe[k]]
    if not vals:
        return {}, None
    f = _scale(vals[0], last_rev)
    vals = [v * f for v in vals]
    if not 0.4 <= vals[0] / last_rev <= 2.5:   # 다음 분기 추정이 실적과 동떨어지면 라벨·단위가 어긋난 것 — 쓰지 않는다
        return {}, None
    out = {shift_q(last_q, i + 1): v for i, v in enumerate(vals[:4])}
    basis = f"분기 컨센서스 {len(out)}개"
    fy = {k: float(v) for k, v in (c.get("rev") or {}).items() if isinstance(v, (int, float)) and v}
    keys = sorted(fy)
    if len(out) == 4 and len(keys) >= 2:
        s4 = sum(vals[:4])
        fyv = {k: fy[k] * _scale(fy[k], s4) for k in keys}
        pair = min(zip(keys, keys[1:]), key=lambda kk: abs(math.log(fyv[kk[0]] / s4)))
        g = fyv[pair[1]] / fyv[pair[0]]
        if 0.3 < g < 4:
            for i in range(4, n):
                out[shift_q(last_q, i + 1)] = out[shift_q(last_q, i - 3)] * g
            basis += f" + 연간 컨센서스 성장률 {pair[0]}→{pair[1]} {g - 1:+.0%}"
    return out, basis


def combine(stat, se_stat, cons, se_cons):
    """분산 역수 가중 결합(Bates & Granger 1969) — (값, 표준오차, 컨센서스 몫)"""
    if cons is None:
        return stat, se_stat, 0.0
    w = se_stat ** 2 / (se_stat ** 2 + se_cons ** 2) if (se_stat ** 2 + se_cons ** 2) > 0 else 0.5
    return w * cons + (1 - w) * stat, math.sqrt(1 / (1 / max(se_stat, 1e-9) ** 2 + 1 / max(se_cons, 1e-9) ** 2)), w


def cons_se(dp, h, fc):
    """h분기 앞 컨센서스 매출의 로그 오차 표준편차 — 애널리스트 범위(최고−최저 ≈ 4σ, Tippett 범위 근사)와 바닥값 중 큰 것, √(h/4)로 늘린다"""
    c = dp.get("consensus") or {}
    rel = []
    for k, v in (c.get("rev") or {}).items():
        lo, hi = (c.get("rev_low") or {}).get(k), (c.get("rev_high") or {}).get(k)
        if isinstance(v, (int, float)) and v and isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and hi > lo:
            rel.append((hi - lo) / 4 / v)
    base = max(fc["cons_se_floor"], min(rel) if rel else 0.0)
    return base * math.sqrt(max(h, 1) / 4)
