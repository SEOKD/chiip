"""Model Lab 의사결정 가치 — 어느 상수가 결론을 가장 많이 흔드는가 (2026-11-08 마스터 지시 "Model Laboratory를 더욱 고도화")

문제: 등록부 상수 321개 중 303개가 사전값인데, 연구 시간은 하루 논문 2~3편뿐이다. 무엇을 먼저 검증할지 기준이 없었다.
방법(국소 민감도, one-at-a-time): 상수 하나를 ±step(기본 10%) 흔들어 v2 밸류에이션을 표본 종목에 다시 돌리고
  ① 기본 시나리오 가치/시총(v0)의 상대 변화 중앙값 ② 매수 매력 신호(강함·보통·약함)가 바뀐 종목 비율 ③ 연 기대수익 변화(%p)를 잰다.
  의사결정 가치 = ① + ② × 2 + |③| — 신호가 바뀌는 상수일수록 검증할 값어치가 크다(정보의 가치, Howard 1966의 단순판).
결과 knowledge/models/lab/sensitivity.csv — model-lab은 상위 상수와 관련된 논문을 먼저 고르고, 그림자 운영(shadow.py) 후보도 여기서 고른다.
대상: 등록부 binding이 config/valuation_v2.yaml#… 이고 값이 숫자인 상수(평가기를 붙인 모델부터 — 다른 모델은 평가기를 붙이면 넓힌다).
사용: py scripts/lab/sensitivity.py [--step 0.1] [--n 12] [--draws 200]
"""
import argparse
import copy
import csv
import random
import statistics
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
OUT = ROOT / "knowledge" / "models" / "lab" / "sensitivity.csv"
CFG = "config/valuation_v2.yaml"


def registry():
    d = yaml.safe_load((ROOT / "knowledge" / "models" / "params" / "registry.yaml").read_text(encoding="utf-8"))
    return d if isinstance(d, list) else d.get("params", [])


def get_path(d, path):
    for k in path:
        d = d[k]
    return d


def set_path(d, path, v):
    for k in path[:-1]:
        d = d[k]
    d[path[-1]] = v


def targets():
    out = []
    cfg = yaml.safe_load((ROOT / CFG).read_text(encoding="utf-8"))
    for p in registry():
        b = str((p or {}).get("binding") or "")
        if not b.startswith(CFG + "#"):
            continue
        path = b.split("#", 1)[1].split(".")
        try:
            v = get_path(cfg, path)
        except (KeyError, TypeError):
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v != 0:
            out.append({"id": p["id"], "path": path, "value": v, "status": p.get("status")})
    return out, cfg


def sample(n, seed=20261108):
    ids = sorted(p.parent.name for p in (ROOT / "knowledge" / "models" / "companies").glob("*/drivers.yaml"))
    random.Random(seed).shuffle(ids)
    return ids[:n]


def outputs(run, eid, cfg, draws):
    random.seed(7)   # 몬테카를로 잡음이 민감도로 섞이지 않게 같은 씨앗
    try:
        import numpy as np
        np.random.seed(7)
    except ImportError:
        pass
    r = run.evaluate(eid, draws, cfg=cfg)
    a = (r.get("decision") or {}).get("attractiveness") or {}
    return {"v0": (r.get("base") or {}).get("v0"), "signal": a.get("signal"), "exp": a.get("exp_return")}


def scan(step=0.1, n=12, draws=200):
    import run
    tg, cfg = targets()
    cos = sample(n)
    base = {}
    for e in cos:
        try:
            base[e] = outputs(run, e, cfg, draws)
        except Exception:
            continue
    rows = []
    for t in tg:
        dv, flips, dexp = [], 0, []
        for sgn in (1, -1):
            c2 = copy.deepcopy(cfg)
            nv = t["value"] * (1 + sgn * step)
            set_path(c2, t["path"], round(nv) if isinstance(t["value"], int) and abs(nv) >= 2 else nv)
            for e, b in base.items():
                try:
                    o = outputs(run, e, c2, draws)
                except Exception:
                    continue
                if b["v0"] and o["v0"] is not None:
                    dv.append(abs(o["v0"] / b["v0"] - 1))
                if o["signal"] != b["signal"]:
                    flips += 1
                if b["exp"] is not None and o["exp"] is not None:
                    dexp.append(abs(o["exp"] - b["exp"]))
        k = max(len(base) * 2, 1)
        med_v = statistics.median(dv) if dv else 0.0
        med_e = statistics.median(dexp) if dexp else 0.0
        rows.append({"param": t["id"], "status": t["status"], "value": t["value"], "dv0_median": round(med_v, 4), "signal_flip_rate": round(flips / k, 3),
                     "dexp_median_pp": round(med_e * 100, 3), "decision_value": round(med_v + 2 * flips / k + med_e, 4)})
    rows.sort(key=lambda r: -r["decision_value"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, ["rank", "param", "status", "value", "dv0_median", "signal_flip_rate", "dexp_median_pp", "decision_value", "as_of", "sample_n", "step"])
        w.writeheader()
        for i, r in enumerate(rows, 1):
            w.writerow({"rank": i, **r, "as_of": date.today().isoformat(), "sample_n": len(base), "step": step})
    return rows, len(base)


def top(k=5):
    if not OUT.exists():
        return []
    with OUT.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))[:k]


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=float, default=0.1)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--draws", type=int, default=200)
    a = ap.parse_args(argv)
    rows, n = scan(a.step, a.n, a.draws)
    print(f"[의사결정 가치] v2 상수 {len(rows)}개 · 표본 {n}종목 · ±{a.step:.0%}")
    for i, r in enumerate(rows[:10], 1):
        print(f"{i:2d}. {r['param']:<38} 가치/시총 변화 {r['dv0_median']:.1%} · 신호 바뀜 {r['signal_flip_rate']:.0%} · 기대수익 {r['dexp_median_pp']:.2f}%p → {r['decision_value']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
