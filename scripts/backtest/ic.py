"""요인 IC 검정·가중 피팅 (ADR-016 §2-3, config/backtest.yaml gates)

입력 패널: [{date, id, <요인>…, fwd}] — fwd = 그 시점 이후 h개월 시장 대비 초과수익(panel.py가 만든다).
1. 월별 순위 IC(스피어먼) → 평균 IC, Newey-West t(겹치는 수익률 자기상관 보정, 시차 11)
2. 채택 관문: |t| ≥ 3.0(Harvey, Liu & Zhu 2016) + 월 수 ≥ 60
3. 기대 IC = 표본 IC × 0.5(McLean & Pontiff 2016 발표 뒤 감쇠) — 알파 v2 블록 ic 제안값
4. walk-forward: 앞 60개월로 IC 부호·크기를 정하고 다음 12개월 표본 외 IC를 잰다
결과는 제안서(knowledge/models/backtest/ic_report.json) — 등록부 값 교체는 scripts/fit 채택 관문을 거친다.
outcomes(): 합성 z와 fwd를 knowledge/models/alpha/outcomes.csv 형식으로 — scripts/alpha/calibrate.py가 보정 곡선을 맞춘다.
"""
import csv
import json
import math
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "alpha"))
import v2  # noqa: E402

REPORT = ROOT / "knowledge" / "models" / "backtest" / "ic_report.json"


def gates():
    return yaml.safe_load((ROOT / "config" / "backtest.yaml").read_text(encoding="utf-8"))["gates"]


def spearman(xs, ys):
    if len(xs) < 5:
        return None
    rx, ry = v2.rank_z(dict(enumerate(xs)), 9), v2.rank_z(dict(enumerate(ys)), 9)
    a, b = [rx[i] for i in range(len(xs))], [ry[i] for i in range(len(ys))]
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    den = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / den if den else None


def monthly_ic(panel, factor, sign=1):
    """[(date, IC)] 날짜순"""
    by = {}
    for r in panel:
        if r.get(factor) is None or r.get("fwd") is None:
            continue
        by.setdefault(r["date"], ([], []))
        by[r["date"]][0].append(sign * float(r[factor]))
        by[r["date"]][1].append(float(r["fwd"]))
    out = []
    for d in sorted(by):
        ic = spearman(*by[d])
        if ic is not None:
            out.append((d, ic))
    return out


def newey_west_t(xs, lags):
    """평균의 Newey-West t(바틀렛 가중)"""
    n = len(xs)
    if n < 3:
        return None
    m = sum(xs) / n
    e = [x - m for x in xs]
    s = sum(v * v for v in e) / n
    for L in range(1, min(lags, n - 1) + 1):
        w = 1 - L / (lags + 1)
        s += 2 * w * sum(e[i] * e[i - L] for i in range(L, n)) / n
    se = math.sqrt(max(s, 1e-18) / n)
    return m / se


def walk_forward(ics, min_train, step):
    """(표본 외 평균 IC, 부호 적중률) — 학습 구간 평균 IC 부호로 다음 step개월 IC에 방향을 매긴다"""
    xs = [x for _, x in ics]
    oos, hits = [], []
    t = min_train
    while t < len(xs):
        sgn = 1 if sum(xs[:t]) >= 0 else -1
        nxt = xs[t:t + step]
        oos += [sgn * x for x in nxt]
        hits += [1 if sgn * x > 0 else 0 for x in nxt]
        t += step
    if not oos:
        return None, None
    return sum(oos) / len(oos), sum(hits) / len(hits)


def test_factor(panel, factor, sign=1, g=None):
    g = g or gates()
    ics = monthly_ic(panel, factor, sign)
    xs = [x for _, x in ics]
    if not xs:
        return {"factor": factor, "months": 0, "verdict": "자료 없음"}
    mean = sum(xs) / len(xs)
    t = newey_west_t(xs, g["newey_west_lags"])
    oos, hit = walk_forward(ics, g["walk_forward"]["min_train"], g["walk_forward"]["step"])
    ok = len(xs) >= g["min_months"] and t is not None and abs(t) >= g["t_hurdle"]
    why = (f"월 {len(xs)} < {g['min_months']}" if len(xs) < g["min_months"] else
           f"|t| {abs(t or 0):.2f} < {g['t_hurdle']}(Harvey·Liu·Zhu)" if not ok else f"|t| {abs(t):.2f} ≥ {g['t_hurdle']}")
    return {"factor": factor, "sign": sign, "months": len(xs), "mean_ic": mean, "nw_t": t, "oos_ic": oos, "oos_hit": hit,
            "expected_ic": mean * g["post_pub_decay"], "pass": ok, "verdict": why}


def report(panel, factors):
    """factors: {factor: sign} — 결과를 ic_report.json으로"""
    g = gates()
    rows = [test_factor(panel, f, s, g) for f, s in factors.items()]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"gates": g, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    return rows


def outcomes(panel, zcol="z", path=None):
    """합성 z와 초과수익 → alpha/outcomes.csv(source=backtest)"""
    path = path or ROOT / "knowledge" / "models" / "alpha" / "outcomes.csv"
    keep = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as fh:
            keep = [r for r in csv.DictReader(fh) if r.get("source") != "backtest"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["date", "id", "z", "excess", "source"])
        w.writeheader()
        w.writerows(keep)
        for r in panel:
            if r.get(zcol) is not None and r.get("fwd") is not None:
                w.writerow({"date": r["date"], "id": r["id"], "z": r[zcol], "excess": r["fwd"], "source": "backtest"})
