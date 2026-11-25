"""Chiip QPX Spot — DDR5 모듈 현물가 두 지표를 큐피엑스(qpx.kr) 가격 페이지에서 모은다
(마스터 지시 2026-11-25 "DRAM 모듈 현물가 리포트는 위 사이트에서 정보를 수집해 그려라 — DDR5 RDIMM 32GB 4800/5600, DDR5 UDIMM 16GB 4800/5600").

원천: qpx.kr/chip/prices/<slug> — 페이지 하단 표기상 원 출처는 TrendForce 공개 가격표, 큐피엑스가 매일 남긴 스냅숏 표(날짜·최고·최저·평균·변화율).
  robots.txt: /chip/prices 허용(막힌 곳은 /chip/admin/, /chip/api/cron/뿐). 약관 제4조: 과도한 자동 요청·무단 복제·배포 금지
  → 6시간에 한 번만 두 페이지를 읽고, 값은 radar/inbox/qpx_spot/(git 제외)에만 두며, 그림은 마스터 개인 봇으로만(TrendForce 승인 조건과 같다).
표는 최근 약 3개월만 보여 준다 — 읽을 때마다 이력에 합쳐 쌓는다(같은 날짜는 새 값이 덮는다).
사용: py radar/qpx_spot.py --update [--force]   # 두 페이지를 읽어 이력에 합친다
      py radar/qpx_spot.py --show               # 지표별 마지막 값
"""
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

OUT = common.ROOT / "radar" / "inbox" / "qpx_spot"
BASE = "https://qpx.kr/chip/prices/"
SERIES = {
    "rdimm32": {"slug": "module-spot__ddr5-rdimm-32gb-4800-5600", "name": "DDR5 RDIMM 32GB 4800/5600"},
    "udimm16": {"slug": "module-spot__ddr5-udimm-16gb-4800-5600", "name": "DDR5 UDIMM 16GB 4800/5600"},
}
FIELDS = ["date", "high", "low", "avg", "chg"]
STATE = "qpx_spot"
EVERY_H = 6
ROW_RE = re.compile(r'<tr><td class="strong mono">(\d{4}-\d{2}-\d{2})</td><td class="num">([\d.,]+)</td><td class="num">([\d.,]+)</td>'
                    r'<td class="num strong">([\d.,]+)</td><td class="num">(.*?)</td></tr>', re.S)
TAG_RE = re.compile(r"<[^>]+>")


def parse(html):
    """가격 페이지 → [{date, high, low, avg, chg}] (변화율이 없으면 빈칸)"""
    rows = {}
    for d, hi, lo, avg, chg in ROW_RE.findall(html):
        c = re.search(r"[+\-−]?\d+(?:\.\d+)?", TAG_RE.sub("", chg).replace("−", "-"))
        rows[d] = {"date": d, "high": float(hi.replace(",", "")), "low": float(lo.replace(",", "")), "avg": float(avg.replace(",", "")),
                   "chg": float(c.group(0)) if c else ""}
    return sorted(rows.values(), key=lambda r: r["date"])


def path(key):
    return OUT / f"{key}.csv"


def read(key):
    p = path(key)
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return [{**r, "avg": float(r["avg"])} for r in csv.DictReader(f) if r.get("avg")]


def merge(key, rows):
    best = {r["date"]: r for r in read(key)}
    best.update({r["date"]: r for r in rows})
    OUT.mkdir(parents=True, exist_ok=True)
    with path(key).open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(best.values(), key=lambda r: r["date"]))
    return len(best)


def points(key, since=None):
    """[(date, 평균)] — since(date) 이후"""
    from datetime import date
    pts = [(date.fromisoformat(r["date"]), r["avg"]) for r in read(key)]
    return [p for p in pts if since is None or p[0] >= since]


def update(force=False):
    """6시간에 한 번만 읽는다(약관 — 과도한 요청 금지). 지표별 {n, last} 또는 {error}"""
    st = common.load_state(STATE, {})
    now = common.now_kst()
    if not force and st.get("at"):
        from datetime import datetime
        if (now - datetime.fromisoformat(st["at"])).total_seconds() < EVERY_H * 3600:
            return {"skipped": st["at"]}
    out = {}
    for key, s in SERIES.items():
        try:
            rows = parse(common.http_get(BASE + s["slug"], timeout=30).decode("utf-8", "ignore"))
            if not rows:
                raise ValueError("표를 찾지 못함(페이지 구조 변경?)")
            out[key] = {"n": merge(key, rows), "last": rows[-1]["date"]}
        except Exception as e:
            out[key] = {"error": f"{type(e).__name__}: {str(e)[:120]}"}
    ok = all("error" not in v for v in out.values())
    common.record_health("src-qpx-spot", ok, "" if ok else json.dumps(out, ensure_ascii=False)[:200])
    st["at"] = common.iso(now)
    common.save_state(STATE, st)
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--update"]:
        print(json.dumps(update(force="--force" in argv), ensure_ascii=False))
    elif argv[:1] == ["--show"]:
        for key, s in SERIES.items():
            r = read(key)
            print(s["name"], r[-1] if r else "없음", f"({len(r)}행)")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
