"""SEC XBRL frames 수집·시점 복원 (ADR-016 §2-3, config/backtest.yaml sec_frames)

frames API = 한 항목(us-gaap 태그)·한 기간의 전 상장사 값. 예) /us-gaap/Assets/USD/CY2019Q4I.json (I = 시점값)
  흐름 항목(매출 등)은 분기 CY2019Q1(3개월)·연간 CY2019, 잔액 항목(자산 등)은 CY2019Q4I.
시점 복원: frames에는 제출일이 없어 기간 종료 + lag_days(분기 45·연간 90일) 뒤부터 '알려진 값'으로 쓴다.
  frames는 같은 기간의 최신 제출값이라 정정 공시가 과거로 스며든다 — 재작성 편향을 결과에 적는다.
저장: knowledge/models/backtest/frames/<태그>_<기간>.csv (cik,name,end,val — git 제외, 재생성 가능)
User-Agent는 radar/pollers/sec_filings._ua() — 마스터 이메일을 넣지 않는다(메모리 규칙).
사용: py scripts/backtest/frames.py --fetch [--from 2011 --to 2025] | --probe Assets CY2019Q4I
"""
import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
CACHE = ROOT / "knowledge" / "models" / "backtest" / "frames"
INSTANT = {"total_assets", "equity", "shares"}


def cfg():
    return yaml.safe_load((ROOT / "config" / "backtest.yaml").read_text(encoding="utf-8"))


def _ua():
    from pollers import sec_filings
    return sec_filings._ua()


def url(tag, period, base):
    tax, _, name = tag.rpartition(":")
    tax = tax or "us-gaap"
    unit = "shares" if name == "EntityCommonStockSharesOutstanding" else "USD"
    return f"{base}/{tax}/{name}/{unit}/{period}.json"


def fetch(tag, period, c=None, force=False):
    """[{cik, name, end, val}] — 캐시 우선. 없는 기간(404)은 빈 목록을 캐시"""
    c = c or cfg()["sec_frames"]
    p = CACHE / f"{tag.replace(':', '_')}_{period}.csv"
    if p.exists() and not force:
        with p.open(encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh))
    req = urllib.request.Request(url(tag, period, c["base"]), headers={"User-Agent": _ua(), "Accept-Encoding": "identity"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        rows = [{"cik": d["cik"], "name": d.get("entityName", ""), "end": d["end"], "val": d["val"]} for d in data.get("data", [])]
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        rows = []
    time.sleep(1 / float(c.get("rate_per_sec", 5)))
    CACHE.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["cik", "name", "end", "val"])
        w.writeheader()
        w.writerows(rows)
    return rows


def periods(y0, y1):
    """(흐름 분기 기간, 연간, 시점값) 목록"""
    out = []
    for y in range(y0, y1 + 1):
        out.append(("annual", f"CY{y}"))
        for q in range(1, 5):
            out.append(("quarter", f"CY{y}Q{q}"))
            out.append(("instant", f"CY{y}Q{q}I"))
    return out


def known_at(end, kind, lag):
    """그 값이 알려진 날 — 기간 종료 + 제출 기한"""
    return date.fromisoformat(end) + timedelta(days=lag["annual" if kind == "annual" else "quarter"])


def fetch_all(y0, y1, log=print):
    c = cfg()["sec_frames"]
    n = 0
    for metric, tags in c["concepts"].items():
        for kind, per in periods(y0, y1):
            if (metric in INSTANT) != (kind == "instant"):
                continue
            for tag in tags:
                rows = fetch(tag, per, c)
                n += 1
                if rows:
                    break
        log(f"- {metric} 완료")
    return n


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--from", dest="y0", type=int, default=2011)
    ap.add_argument("--to", dest="y1", type=int, default=2025)
    ap.add_argument("--probe", nargs=2)
    a = ap.parse_args(argv)
    if a.probe:
        rows = fetch(a.probe[0], a.probe[1])
        print(f"{a.probe[0]} {a.probe[1]}: {len(rows)}개 회사" + (f", 예: {rows[0]['name']} {rows[0]['end']} {rows[0]['val']}" if rows else ""))
        return 0
    if a.fetch:
        print(f"요청 {fetch_all(a.y0, a.y1)}건(캐시 포함)")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))
