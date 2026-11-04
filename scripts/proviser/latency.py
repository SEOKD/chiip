"""Pulse 시의성 장부 (마스터 지시 2026-11-04 "시의성 3/10 → 실시간급") — 개선이 실제로 먹혔는지 숫자로 본다

radar/pulse/YYYYMMDD_*.json(펄스 회차 출력)에서 원본 유형별로
  감지 지연 = detected_at − published_at (수집 주기·원천 지연)
  집어 듦 지연 = run_at − detected_at (판단 회차가 원본을 잡기까지 — 앱 예약·긴급 문턱)
중앙값·상위 10%를 docs/proviser/latency.csv에 하루 한 줄씩(유형별) 남긴다. Proviser가 시의성 점수의 근거로 읽는다.
텔레그램(2차 재게시)은 빠르게 보이지만 원본이 아니라 따로 둔다.
사용: py scripts/proviser/latency.py [YYYYMMDD]   (기본: 어제·오늘)
"""
import csv
import glob
import json
import statistics as st
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "proviser" / "latency.csv"
KST = timezone(timedelta(hours=9))


def q90(v):
    v = sorted(v)
    return v[max(0, int(0.9 * len(v)) - 1)]


def ts(x):
    t = datetime.fromisoformat(x)
    return t if t.tzinfo else t.replace(tzinfo=KST)


def day_rows(day):
    det, pick = {}, {}
    seen = set()
    for f in sorted(glob.glob(str(ROOT / "radar" / "pulse" / f"{day}_*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        run = ts(d["run_at"])
        for s in d.get("sources", []):
            key = s.get("url") or s.get("title")
            if key in seen:   # 같은 원본이 여러 회차에 실리면 처음만
                continue
            seen.add(key)
            if len(str(s.get("published_at") or "")) <= 10:   # 날짜만 있는 원본(SEC 전문 검색 file_date 등)은 지연을 잴 수 없다
                continue
            try:
                p, q = ts(s["published_at"]), ts(s["detected_at"])
            except (KeyError, TypeError, ValueError):
                continue
            c = s.get("source_class", "?")
            det.setdefault(c, []).append(max(0.0, (q - p).total_seconds() / 60))
            pick.setdefault(c, []).append(max(0.0, (run - q).total_seconds() / 60))
    return [[day, c, len(v), round(st.median(v), 1), round(q90(v), 1), round(st.median(pick[c]), 1), round(q90(pick[c]), 1)]
            for c, v in sorted(det.items(), key=lambda kv: -len(kv[1]))]


def write(days):
    old = []
    if OUT.exists():
        with OUT.open(encoding="utf-8", newline="") as f:
            old = [r for r in csv.reader(f)][1:]
    old = [r for r in old if r[0] not in days]
    new = [r for d in days for r in day_rows(d)]
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "class", "n", "detect_med_min", "detect_p90_min", "pickup_med_min", "pickup_p90_min"])
        w.writerows(sorted(old + new, key=lambda r: (r[0], r[1])))
    return new


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    today = datetime.now(KST)
    days = argv or [(today - timedelta(days=1)).strftime("%Y%m%d"), today.strftime("%Y%m%d")]
    for r in write(days):
        print(r)


if __name__ == "__main__":
    main(sys.argv[1:])
