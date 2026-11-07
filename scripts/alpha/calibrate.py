"""알파 v2 확률 보정·성적표 (ADR-016 §2-2 6단계, config/alpha_v2.yaml calibration)

관측: knowledge/models/alpha/outcomes.csv (열 date,id,z,excess,source) — excess = 판정 기간(1년) 시장 대비 초과수익.
  원천 두 가지: ① 실시간 — v2_shadow.csv의 z와 만기 시점 수익률(scripts/backtest/prices 원천 승인 후 자동)
               ② 백테스트 — scripts/backtest/ic.py가 과거 시점 복원으로 만든 (z, excess)
보정: 관측 ≥ platt_min_n이면 로지스틱(Platt 1999) P(excess > 0) = σ(a + b·z), ≥ isotonic_min_n이면 등위(PAV) 회귀를 같이 적고
      월간 브라이어 점수·신뢰도 구간표를 낸다. 결과 knowledge/models/alpha/calibration.json — v2.p_beat가 읽는다.
관측이 모자라면 '자료 대기'만 적고 사전 곡선(이변량 정규 Φ(IC·z/√(1−IC²)))을 그대로 둔다.
사용: py scripts/alpha/calibrate.py [--fit]
"""
import argparse
import csv
import json
import math
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "fit"))
import harness  # noqa: E402

OUTCOMES = ROOT / "knowledge" / "models" / "alpha" / "outcomes.csv"
CALIB = ROOT / "knowledge" / "models" / "alpha" / "calibration.json"


def platt(z, y, iters=50):
    """로지스틱 회귀(뉴턴법) — (a, b)"""
    a = b = 0.0
    for _ in range(iters):
        ga = gb = haa = hab = hbb = 0.0
        for zi, yi in zip(z, y):
            p = 1 / (1 + math.exp(-(a + b * zi)))
            w = p * (1 - p)
            ga += yi - p
            gb += (yi - p) * zi
            haa += w
            hab += w * zi
            hbb += w * zi * zi
        det = haa * hbb - hab * hab
        if det <= 1e-12:
            break
        da, db = (hbb * ga - hab * gb) / det, (haa * gb - hab * ga) / det
        a, b = a + da, b + db
        if abs(da) + abs(db) < 1e-9:
            break
    return a, b


def isotonic(z, y):
    """등위 회귀(PAV) — [(z 상한, 확률)] 계단"""
    pts = sorted(zip(z, y))
    blocks = [[zi, float(yi), 1] for zi, yi in pts]   # [최대 z, 합, 개수]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][1] / blocks[i][2] > blocks[i + 1][1] / blocks[i + 1][2]:
            blocks[i] = [blocks[i + 1][0], blocks[i][1] + blocks[i + 1][1], blocks[i][2] + blocks[i + 1][2]]
            del blocks[i + 1]
            i = max(i - 1, 0)
        else:
            i += 1
    return [(b[0], b[1] / b[2]) for b in blocks]


def load():
    if not OUTCOMES.exists():
        return [], []
    z, y = [], []
    with OUTCOMES.open(encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            try:
                z.append(float(r["z"]))
                y.append(1 if float(r["excess"]) > 0 else 0)
            except (KeyError, ValueError):
                continue
    return z, y


def fit(c=None):
    c = c or yaml.safe_load((ROOT / "config" / "alpha_v2.yaml").read_text(encoding="utf-8"))["calibration"]
    z, y = load()
    if len(z) < c["platt_min_n"]:
        return {"method": "prior", "n": len(z), "note": f"자료 대기 — 만기 관측 {len(z)} < {c['platt_min_n']}"}
    a, b = platt(z, y)
    probs = [1 / (1 + math.exp(-(a + b * zi))) for zi in z]
    out = {"method": "platt", "a": round(a, 4), "b": round(b, 4), "n": len(z), "as_of": date.today().isoformat(),
           "brier": round(harness.brier(probs, y), 4), "base_rate": round(sum(y) / len(y), 3), "reliability": harness.calibration(probs, y)}
    if len(z) >= c["isotonic_min_n"]:
        out["isotonic"] = isotonic(z, y)
    return out


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", action="store_true")
    a = ap.parse_args(argv)
    r = fit()
    print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    if a.fit and r["method"] != "prior":
        CALIB.write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
