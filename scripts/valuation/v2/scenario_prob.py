"""시나리오 확률(약세·기본·강세)을 근거로 계산한다 (마스터 지시 2026-11-14 "약세와 강세 확률이 각 25%씩으로 계산이 많이 되는데 이 확률 체계를 다시 점검하라")

점검 결과(ADR-035): 76개 Analysis 리포트의 확률이 네 가지 틀(25/50/25 35건·30/50/20 21건·30/45/25 15건·35/45/20 5건)에만 있었다.
모델이 고른 반올림 숫자였고(datapack scenario_probs 74/114), 없으면 어닝콜 톤 규칙(상향 20/50/30·보합 25/50/25·하향 30/50/20)이었다 —
시나리오 숫자(성장률 폭)나 불확실성과 연결되지 않았다.

방식: 다음 회계연도 매출 성장률 g의 분포 F를 만들고, 시나리오 성장률(약세 g_b < 기본 g_0 < 강세 g_u)의 중간점에서 자른다.
  P(약세) = F((g_b + g_0)/2), P(강세) = 1 − F((g_0 + g_u)/2), P(기본) = 나머지
  F = (1 − w)·내부 관점 + w·외부 관점(참조 집단 예측 — 내부 관점만 쓰면 낙관으로 기운다, Kahneman·Lovallo 1993; Mauboussin 2016 기저율)
  내부 관점 = 정규(평균 = 컨센서스 성장률, 표준편차 = 추정 범위(최고 − 최저) ÷ d2(n) × 팽창 계수, 하한 sigma_floor)
    d2(n) = 정규 표본 n개의 범위 기댓값 ÷ σ(통계적 공정관리 관리도 상수) — 애널리스트 n명의 최고·최저로 σ를 잰다
  외부 관점 = 같은 규모 구간 미국 상장사의 실제 1년 매출 성장률 경험 분포(scripts/valuation/v2/baserates.py, SEC 일괄 표본)
확률은 0.05 단위, 각 5% 이상. 상수는 config/scenario_prob.yaml(등록부 prm-sp-*).
"""
import bisect
import math
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
D2 = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534, 7: 2.704, 8: 2.847, 9: 2.970, 10: 3.078, 12: 3.258, 15: 3.472, 20: 3.735, 25: 3.931}
_OUT = {}


def cfg():
    return yaml.safe_load((ROOT / "config" / "scenario_prob.yaml").read_text(encoding="utf-8"))["scenario_prob"]


def d2(n):
    """관리도 상수 d2 — 표에 없는 n은 가까운 아래 값"""
    if not n or n < 2:
        return None
    keys = sorted(D2)
    return D2[max(k for k in keys if k <= n)] if n < keys[-1] else D2[keys[-1]]


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def outside(start_rev_usd):
    """같은 규모 구간의 실제 1년 매출 성장률(정렬) — 프로세스 안에서 한 번만 읽는다"""
    import baserates
    if not baserates.BULK.exists():   # 지금 표본(AI 밸류체인 생존 40종목)은 고성장 쪽으로 치우쳐 외부 관점으로 쓰지 않는다 — sec_bulk.py 뒤에 켜진다
        return [], "SEC 전 상장사 표본 없음"
    if "sample" not in _OUT:
        _OUT["sample"] = baserates.windows(1)
    lo, hi, name = baserates.bucket_of(start_rev_usd)
    xs = sorted(c for r, c in _OUT["sample"] if lo <= r < hi)
    if len(xs) < 30:
        xs, name = sorted(c for _, c in _OUT["sample"]), "전체"
    return xs, name


def ecdf(xs, x):
    return bisect.bisect_right(xs, x) / len(xs) if xs else None


def inside_sigma(rev0, lo, hi, n, c, g=0.0):
    """추정 범위로 잰 내부 관점 표준편차(성장률 단위). 범위가 없으면 base + per_growth × |g|"""
    if lo is None or hi is None or not rev0 or hi <= lo or not d2(n):
        nr = c["no_range"]
        return max(c["sigma_floor"], nr["base"] + nr["per_growth"] * abs(g)), f"추정 범위 없음 — {nr['base']:.0%} + {nr['per_growth']} × |성장률|"
    s = (hi - lo) / rev0 / d2(n) * c["dispersion_inflate"]
    return max(s, c["sigma_floor"]), f"범위 {(hi - lo) / rev0:.1%} ÷ d2({n}) × {c['dispersion_inflate']}"


def _round(p, c):
    step, floor = c["round_to"], c["min_prob"]
    b = max(floor, round(p["bear"] / step) * step)
    u = max(floor, round(p["bull"] / step) * step)
    if b + u > 1 - floor:   # 기본이 하한 밑으로 가지 않게
        k = (1 - floor) / (b + u)
        b, u = round(b * k / step) * step, round(u * k / step) * step
    return {"bear": round(b, 2), "base": round(1 - b - u, 2), "bull": round(u, 2)}


def compute(g, gb, gu, rev0, lo=None, hi=None, n=None, start_rev_usd=None, c=None, out_sample=None):
    """g·gb·gu = 기본·약세·강세 다음 해 매출 성장률, rev0 = 기준 매출, lo·hi = 다음 해 컨센서스 최저·최고 매출, n = 애널리스트 수.
    반환 {bear, base, bull, why, parts}. 순서가 맞지 않으면(약세 < 기본 < 강세가 아니면) None"""
    c = c or cfg()
    if None in (g, gb, gu) or not (gb < g < gu):
        return None
    sig, sig_why = inside_sigma(rev0, lo, hi, n, c, g)
    if out_sample is not None:
        xs, bname = sorted(out_sample), "주어진 표본"
    else:
        xs, bname = outside(start_rev_usd or 0)
    w = c["outside_weight"] if xs else 0.0
    c1, c2 = (gb + g) / 2, (g + gu) / 2
    F = lambda x: (1 - w) * phi((x - g) / sig) + (w * ecdf(xs, x) if xs else 0.0)
    raw = {"bear": F(c1), "bull": 1 - F(c2)}
    raw["base"] = 1 - raw["bear"] - raw["bull"]
    p = _round(raw, c)
    med = xs[len(xs) // 2] if xs else None
    why = (f"다음 해 매출 성장 분포로 계산 — 약세 {c1:+.1%} 아래·강세 {c2:+.1%} 위 확률. 내부 관점(컨센서스 {g:+.1%}, σ {sig:.1%}: {sig_why}) {1 - w:.0%}"
           + (f" + 외부 관점(같은 규모 {bname} 실제 1년 성장, 중앙값 {med:+.1%}) {w:.0%}" if xs else f" — 외부 관점 꺼짐({bname})"))
    return {**p, "why": why, "parts": {"raw": {k: round(v, 3) for k, v in raw.items()}, "sigma": round(sig, 4), "cuts": [round(c1, 4), round(c2, 4)],
                                        "outside_weight": w, "outside_median": med}}


def judged(engine, model, why, c=None):
    """모델 확률(datapack scenario_probs)을 엔진 확률 ± judge_cap 안으로 묶는다. 이유가 없으면 엔진 그대로"""
    c = c or cfg()
    if not model or not why:
        return {k: engine[k] for k in ("bear", "base", "bull")}, None
    cap = c["judge_cap"]
    b = min(max(model.get("bear", engine["bear"]), engine["bear"] - cap), engine["bear"] + cap)
    u = min(max(model.get("bull", engine["bull"]), engine["bull"] - cap), engine["bull"] + cap)
    b, u = max(b, c["min_prob"]), max(u, c["min_prob"])
    if 1 - b - u < c["min_prob"]:   # 기본 확률이 하한 밑(음수 포함)이면 약세·강세를 같은 비율로 줄인다(2026-11-14 점검: 기본 −0.10이 몬테카를로 가중으로 들어갔다)
        k = (1 - c["min_prob"]) / (b + u)
        b, u = b * k, u * k
    return {"bear": round(b, 2), "base": round(1 - round(b, 2) - round(u, 2), 2), "bull": round(u, 2)}, why


def _start(spec):
    if isinstance(spec, list):
        return spec[0] if spec else None
    return (spec or {}).get("start")


def apply(co, dp):
    """drivers(co)의 시나리오 확률을 근거 계산값으로 바꾼다(제자리). datapack scenario_probs는 ±judge_cap 안의 조정으로만.
    계산할 수 없으면(약세 < 기본 < 강세가 아니거나 재료 없음) 기존 확률을 두고 사유를 남긴다. 반환 co['scenario_prob']"""
    sc = co.get("scenarios") or {}
    if not all(k in sc for k in ("bear", "base", "bull")):
        return None
    cons = (dp or {}).get("consensus") or {}
    keys = sorted(cons.get("rev") or {})
    nxt = keys[1] if len(keys) > 1 else (keys[0] if keys else None)
    lo, hi = (cons.get("rev_low") or {}).get(nxt), (cons.get("rev_high") or {}).get(nxt)
    g, gb, gu = (_start(sc[k]["growth"]) for k in ("base", "bear", "bull"))
    r = compute(g, gb, gu, co.get("rev0"), lo, hi, cons.get("n_analysts"), (co.get("rev0") or 0) * float(co.get("unit_usd") or 1e9))
    if not r:
        co["scenario_prob"] = {"status": "계산 불가", "why": f"성장률 순서가 약세 {gb} < 기본 {g} < 강세 {gu}가 아니다 — 동인 재생성(build_drivers) 필요", "probs": {k: sc[k].get("prob") for k in sc}}
        return co["scenario_prob"]
    probs, mwhy = judged(r, (dp or {}).get("scenario_probs"), (dp or {}).get("scenario_probs_why"))
    for k in ("bear", "base", "bull"):
        sc[k]["prob"] = probs[k]
    co["scenario_prob"] = {"status": "계산", "engine": {k: r[k] for k in ("bear", "base", "bull")}, "probs": probs, "why": r["why"], "judge": mwhy, "parts": r["parts"]}
    return co["scenario_prob"]
