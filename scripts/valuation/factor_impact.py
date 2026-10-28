"""요인별 밸류에이션 영향 분해 (BUILD_PROMPT §21.14 — 실적·콜 요인을 -10~+10 점수로 정량화)

기업 모델 모듈(knowledge/models/companies/<id>/model.py)은 value(drivers) → {"per_share": .., ...}를 제공한다.
기준 동인(이전 정보 집합) → 요인 하나씩 바꿔 가치 변화를 잰다.
  - 단독(standalone): 기준에서 그 요인만 적용했을 때 Δ%
  - 순차(sequential): 앞 요인들을 누적 적용한 상태에서 추가 Δ% (합이 전체 변화와 같다 — 상호작용 포함)
  - 확신도 가중: Δ% × 확신도(0~1, 확정사실 1.0 · 가이던스 0.8 · 경영진 목표·전망 0.5 · 정황 0.3)
점수 = clip(확신도 가중 Δ% / pct_per_point, -10, 10). 기본 pct_per_point = 2.0 → ±10점 = 주당가치 ±20%.
사용: py scripts/valuation/factor_impact.py <entity> [--pct-per-point 2]
"""
import argparse
import copy
import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_model(entity):
    d = ROOT / "knowledge" / "models" / "companies" / entity
    spec = importlib.util.spec_from_file_location(f"model_{entity}", d / "model.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cfg = yaml.safe_load((d / "factors.yaml").read_text(encoding="utf-8"))
    return mod, cfg


def apply(drivers, changes, deltas=None):
    """changes = 절대값으로 바꿈, deltas = 현재값에 더함(앞 요인을 덮어쓰지 않아야 할 때 — 예: 둔화 신호)"""
    out = copy.deepcopy(drivers)
    for k, v in changes.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    for k, v in (deltas or {}).items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                out[k][kk] = out[k][kk] + vv
        else:
            out[k] = out[k] + v
    return out


def score(delta_pct, conf, pct_per_point):
    return max(-10.0, min(10.0, delta_pct * conf / pct_per_point))


def run(entity, pct_per_point=2.0):
    mod, cfg = load_model(entity)
    base = mod.BASE
    v0 = mod.value(base)["per_share"]
    rows, cur = [], base
    for f in cfg["factors"]:
        alone = mod.value(apply(base, f.get("changes", {}), f.get("deltas")))["per_share"]
        nxt = apply(cur, f.get("changes", {}), f.get("deltas"))
        seq = mod.value(nxt)["per_share"]
        prev = mod.value(cur)["per_share"]
        d_alone = (alone / v0 - 1) * 100
        d_seq = (seq / prev - 1) * 100
        conf = float(f.get("confidence", 1.0))
        rows.append({"id": f["id"], "label": f["label"], "kind": f.get("kind", ""), "conf": conf,
                     "d_alone": d_alone, "d_seq": d_seq, "score": score(d_alone, conf, pct_per_point)})
        cur = nxt
    v1 = mod.value(cur)
    return v0, v1, rows


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("entity")
    ap.add_argument("--pct-per-point", type=float, default=2.0)
    a = ap.parse_args(argv)
    v0, v1, rows = run(a.entity, a.pct_per_point)
    print(f"[요인 영향] {a.entity} 기준 주당가치 {v0:.2f} → 전 요인 반영 {v1['per_share']:.2f} ({(v1['per_share']/v0-1)*100:+.1f}%)")
    print(f"{'id':5} {'단독Δ%':>7} {'순차Δ%':>7} {'확신':>4} {'점수':>5}  요인")
    for r in rows:
        print(f"{r['id']:5} {r['d_alone']:7.1f} {r['d_seq']:7.1f} {r['conf']:4.1f} {r['score']:5.1f}  {r['label']} [{r['kind']}]")
    tot = sum(r["d_alone"] * r["conf"] for r in rows)
    print(f"합계(확신도 가중 단독Δ%) {tot:+.1f}% → 종합 점수 {score(tot, 1.0, a.pct_per_point):+.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
