"""페어별 역방향 신호 삼각측량 (BUILD_PROMPT §11.6) — 계산만, 해석은 triangulator 에이전트

radar/reverse/signals/**/*.yaml 을 pair_id별로 모아
- 독립성: (layer, origin_id) 쌍이 다르면 독립. 같은 origin_id는 한 번만.
- 점수: config/signal_rules.yaml weights 합
- 경보: 수렴(독립 S2≥2 또는 S1≥2+S2≥1) / 단독(S3) / T0 S4 이상
사용: py scripts/triangulate.py [pair_id]
"""
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ORDER = ["S0", "S1", "S2", "S3", "S4", "S5"]


def load_signals():
    out = []
    for f in (ROOT / "radar" / "reverse" / "signals").rglob("*.yaml"):
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if d.get("pair_id") and d.get("status") not in ("부정", "만료"):
            out.append(d)
    return out


def assess(signals, rules):
    w = rules.get("weights", {})
    seen_origin, independent = set(), []
    for s in sorted(signals, key=lambda x: ORDER.index(x.get("strength", "S0")), reverse=True):
        origin = s.get("origin_id") or s.get("id")
        if origin in seen_origin:
            continue
        seen_origin.add(origin)
        independent.append(s)
    score = sum(w.get(s.get("strength", "S0"), 0) for s in independent)
    count = defaultdict(int)
    layers = defaultdict(set)
    for s in independent:
        count[s["strength"]] += 1
        layers[s["strength"]].add(s.get("layer"))
    strongest = max((s.get("strength", "S0") for s in independent), key=ORDER.index, default="S0")
    alert = "해당없음"
    if ORDER.index(strongest) >= 4:
        alert = "단독경보(S4+)→P0"
    elif strongest == "S3":
        alert = "단독경보(S3)→P1"
    elif (count["S2"] >= 2 and len(layers["S2"]) >= 2) or (count["S1"] >= 2 and count["S2"] >= 1):
        alert = "수렴경보→P1"
    return {"independent": len(independent), "score": score, "strongest": strongest, "alert": alert,
            "layers": sorted({s.get("layer") for s in independent})}


def main(argv):
    rules = yaml.safe_load((ROOT / "config" / "signal_rules.yaml").read_text(encoding="utf-8")) or {}
    by_pair = defaultdict(list)
    for s in load_signals():
        by_pair[s["pair_id"]].append(s)
    targets = [argv[0]] if argv else sorted(by_pair)
    if not targets:
        print("신호 없음")
    for pid in targets:
        r = assess(by_pair.get(pid, []), rules)
        print(f"{pid}: 독립 {r['independent']} / 점수 {r['score']} / 최강 {r['strongest']} / 레이어 {r['layers']} / {r['alert']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
