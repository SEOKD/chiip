"""레이더 성능 (BUILD_PROMPT §17.3) — 주간
탐지 지연(게시→탐지), 등급 분포, 수집 장애, 누락(radar_misses.csv)
사용: py scripts/score_radar.py [일수=7]
"""
import json
import sys
from collections import Counter
from datetime import datetime

import yaml
from score_common import ROOT, parse_date, read_csv, since


def main(argv):
    days = int(argv[0]) if argv else 7
    start = since(days)
    lat, levels, first_src = [], Counter(), Counter()
    for f in (ROOT / "radar" / "cards").rglob("*.yaml"):
        c = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        d = parse_date(str(c.get("detected_at", "")))
        if not d or d < start:
            continue
        levels[c.get("alert_level", "?")] += 1
        first_src[c.get("first_seen_source", "?")] += 1
        try:
            a = datetime.fromisoformat(str(c["published_at"]))
            b = datetime.fromisoformat(str(c["detected_at"]))
            if a.tzinfo and b.tzinfo:
                lat.append((b - a).total_seconds() / 60)
        except (KeyError, ValueError):
            pass
    health = {}
    hp = ROOT / "radar" / "state" / "health.json"
    if hp.exists():
        health = json.loads(hp.read_text(encoding="utf-8"))
    misses = [m for m in read_csv("evals/radar_misses.csv") if (parse_date(m["date_seen"]) or start) >= start]
    print(f"[레이더 성능 최근 {days}일]")
    print(f"- 카드 {sum(levels.values())}건: " + ", ".join(f"{k} {v}" for k, v in sorted(levels.items())))
    if lat:
        lat.sort()
        print(f"- 탐지 지연(분): 중앙값 {lat[len(lat)//2]:.0f}, 최대 {lat[-1]:.0f}  (T0 목표: 탐지 5분)")
    print("- 최초 포착 원천: " + ", ".join(f"{k} {v}" for k, v in first_src.most_common(5)))
    bad = {k: v for k, v in health.items() if v.get("error_count", 0) > 0}
    print(f"- 수집 장애 원천 {len(bad)}개: " + ", ".join(f"{k}({v['error_count']})" for k, v in bad.items()))
    print(f"- 누락 기록 {len(misses)}건: " + ", ".join(Counter(m.get("cause", "?") for m in misses).keys()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))