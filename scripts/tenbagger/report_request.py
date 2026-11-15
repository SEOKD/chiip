"""요청 리포트 대기열 (마스터 지시 2026-11-15 "Sekio Giken 리포트 하나 써라. Pulse가 이를 수행하라. Analysis 주기에 카운트하지마라")

마스터가 직접 요청한 Analysis 리포트를 주말 Pulse 회차(chiip-pulse-weekend)가 쓴다. 정기 Analysis 회차(pick_report)의 순번·할당량(log.csv)에는 넣지 않고
requests_log.csv에만 남긴다. 같은 종목을 30일 안에 정기 회차가 다시 고르지 않도록 pick_report.recent가 이 장부도 읽는다.
사용: py scripts/tenbagger/report_request.py --add "<이름>" [--id <entity id>] [--ticker <코드>] [--market jp|us|kr|tw|eu] [--note "<메모>"]
      py scripts/tenbagger/report_request.py --due                   # 쓸 요청(오래된 순)
      py scripts/tenbagger/report_request.py --done <이름|id> <html 경로> "<치입 판단 한 줄>"
"""
import csv
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REP = ROOT / "outputs" / "tenbagger" / "reports"
QUEUE = REP / "requests.json"
LOG = REP / "requests_log.csv"
FIELDS = ["date", "id", "ticker", "html", "view", "name"]
KST = timezone(timedelta(hours=9))


def now():
    return datetime.now(KST)


def load():
    return json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.exists() else []


def save(q):
    REP.mkdir(parents=True, exist_ok=True)
    QUEUE.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")


def add(name, eid=None, ticker=None, market=None, note=None):
    q = load()
    for x in q:
        if x["status"] == "대기" and (x["name"] == name or (eid and x.get("id") == eid)):
            return False
    q.append({"name": name, "id": eid, "ticker": ticker, "market": market, "note": note, "asked": now().isoformat(timespec="minutes"), "status": "대기"})
    save(q)
    return True


def due():
    return [x for x in load() if x["status"] == "대기"]


def status(at=None):
    """Pulse 관문용 — 주말(토·일 KST) 회차에서만 due(마스터 지시 2026-11-15 "Pulse 말고 Pulse Weekend로 수행하라"). 주중엔 대기만 표시"""
    d = due()
    weekend = (at or now()).weekday() >= 5
    return {"due": bool(d) and weekend, "items": d if weekend else [], "waiting": len(d), "runs_on": "chiip-pulse-weekend"}


def done(key, html, view):
    q = load()
    hit = next((x for x in q if x["status"] == "대기" and key in (x["name"], x.get("id"), x.get("ticker"))), None)
    if not hit:
        raise SystemExit(f"대기 요청 없음: {key}")
    hit.update(status="완료", done=now().isoformat(timespec="minutes"), html=html)
    save(q)
    new = not LOG.exists()
    with LOG.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({"date": now().date().isoformat(), "id": hit.get("id") or "", "ticker": hit.get("ticker") or "", "html": html, "view": view, "name": hit["name"]})
    return hit


def recent_ids(cut_iso):
    """pick_report.recent용 — cut 이후 요청 리포트의 id·티커"""
    if not LOG.exists():
        return set()
    with LOG.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["date"] >= cut_iso]
    return {r["id"] for r in rows if r.get("id")} | {r["ticker"] for r in rows if r.get("ticker")}


def main(argv):
    def opt(k):
        return argv[argv.index(k) + 1] if k in argv else None
    if "--add" in argv:
        ok = add(opt("--add"), opt("--id"), opt("--ticker"), opt("--market"), opt("--note"))
        print("추가" if ok else "이미 대기 중")
    elif "--due" in argv:
        print(json.dumps(due(), ensure_ascii=False, indent=1))
    elif "--done" in argv:
        i = argv.index("--done")
        print(json.dumps(done(argv[i + 1], argv[i + 2], argv[i + 3]), ensure_ascii=False))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
