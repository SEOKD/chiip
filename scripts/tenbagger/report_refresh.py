"""어닝콜 전문 반영 재발행 (마스터 지시 2026-10-31 "어닝콜 스크립트가 아직 안 나온 종목이면 나중에 업데이트됐을 때 리포트에 이를 반영해
다시 발행하는 구조를 엔진에 넣어라") — 결정론, 판단과 글은 모델

대상: 최근 리포트 중 발행 시점에 이미 콜이 끝났는데 데이터 묶음의 call이 그 콜보다 오래된 것.
전문 상태는 radar/transcript_watch.py 장부(radar/state/transcripts.json)를 그대로 쓴다 — 펄스 회차가 전문 신규 게재를 확인한다.
  대기 = 전문이 아직 없다 / 재발행 = 전문이 올라왔다 / 만료 = 10일이 지나도 없다
+ 실적 업데이트(마스터 지시 2026-11-12 "기존에 Analysis 리포트에서 다뤘던 종목은 재무 결과 및 어닝콜 스크립트가 모두 공개되면 새로 업데이트하는 구조"):
  다룬 적 있는 모든 종목(나이 제한 없음, 종목별 최신 리포트)에서 리포트 발행 뒤에 다음 분기 콜이 열렸고 전문이 올라왔으면(장부 found·done) 대상.
  재무제표는 모델이 회차에서 Fiscal.ai로 그 분기 손익이 올라왔는지 확인한다 — 아직이면 --wait-fin으로 하루 미룬다(콜 뒤 21일까지).
  한국 상장사(XKRX_)는 전문이 없어 이 경로에서 빠진다.
기록: outputs/tenbagger/reports/reissue.csv(time,stem,ticker,event,note) — 같은 콜로 두 번 재발행하지 않는다.
사용: py scripts/tenbagger/report_refresh.py --status            # 전체 상태
      py scripts/tenbagger/report_refresh.py --due               # 재발행할 리포트(오래된 순)
      py scripts/tenbagger/report_refresh.py --start <stem>      # 재발행 시작 — 발행 상태를 되돌리고 기존 Artifact·노션 주소를 돌려준다
      py scripts/tenbagger/report_refresh.py --done <stem> <event> "<바뀐 것 한 줄>"
      py scripts/tenbagger/report_refresh.py --wait-fin <stem> <event>   # 실적 업데이트 대상인데 재무제표가 아직 없다 — 24시간 뒤 다시
"""
import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REP = ROOT / "outputs" / "tenbagger" / "reports"
LOG = REP / "log.csv"
DONE = REP / "reissue.csv"
DELIVERY = REP / "delivery"
EVENTS = ROOT / "radar" / "state" / "transcripts.json"
COMPANIES = ROOT / "knowledge" / "models" / "companies"
WINDOW_DAYS = 14      # 전문 대기 10일 + 여유. 이보다 오래된 리포트는 다시 내지 않는다
PT_ONLY = ("XKRX_",)  # 한국은 전문을 기다리지 않는다(당기·직전 PT 기준)
NOTE_H2 = "재발행 기록"
WAIT_FIN = REP / "update_wait.json"
UPDATE_MAX_DAYS = 21   # 콜 뒤 이 기간 안에 재무제표·전문이 다 나오지 않으면 다음 분기를 기다린다
LABEL = {"wait": "대기", "found": "재발행", "done": "재발행", "expired": "만료"}
KST = timezone(timedelta(hours=9))


def reports(today, root=REP):
    """종목별 최신 리포트(WINDOW_DAYS 안)"""
    if not (root / "log.csv").exists():
        return []
    with (root / "log.csv").open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("html") and r.get("id")]
    latest = {}
    for r in rows:
        if (today - date.fromisoformat(r["date"])).days <= WINDOW_DAYS:
            latest[r["ticker"].upper()] = r
    return list(latest.values())


def covered(root=REP):
    """다룬 적 있는 모든 종목의 최신 리포트(나이 제한 없음)"""
    if not (root / "log.csv").exists():
        return []
    with (root / "log.csv").open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("html") and r.get("id")]
    latest = {}
    for r in rows:
        k = r["ticker"].upper()
        if k not in latest or r["date"] >= latest[k]["date"]:
            latest[k] = r
    return list(latest.values())


def next_event(rep, events, today):
    """리포트 발행 뒤에 열린 콜 중 전문이 올라온 가장 최근 건(콜 뒤 UPDATE_MAX_DAYS 안)"""
    hits = [e for e in events.values() if (e.get("id") == rep["id"] or str(e.get("ticker") or "").upper() == rep["ticker"].upper())
            and not e["key"].startswith(PT_ONLY) and e["date"] > rep["date"] and e.get("status") in ("found", "done")
            and 0 <= (today - date.fromisoformat(e["date"])).days <= UPDATE_MAX_DAYS]
    return max(hits, key=lambda e: e["date"], default=None)


def _waits(path=None):
    path = path or WAIT_FIN
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def updates(today=None, root=REP, events_file=EVENTS, now=None):
    today = today or datetime.now(KST).date()
    now = now or datetime.now(KST)
    events = json.loads(events_file.read_text(encoding="utf-8")).get("events", {}) if events_file.exists() else {}
    seen, waits, out = reissued(root / "reissue.csv"), _waits(root / "update_wait.json"), []
    for rep in covered(root):
        e = next_event(rep, events, today)
        if not e:
            continue
        stem = Path(rep["html"]).stem
        if (stem, e["event"]) in seen:
            continue
        w = waits.get(f"{stem}|{e['event']}")
        out.append({"stem": stem, "json": f"outputs/tenbagger/reports/{stem}.json", "id": rep["id"], "ticker": rep["ticker"], "key": e["key"], "event": e["event"],
                    "call_date": e["date"], "report_date": rep["date"], "kind": "실적 업데이트",
                    "state": "재무 대기" if w and w > now.isoformat(timespec="seconds") else "재발행"})
    return sorted(out, key=lambda r: r["call_date"])


def wait_fin(stem, event, root=REP, now=None):
    now = now or datetime.now(KST)
    path = root / "update_wait.json"
    w = _waits(path)
    w[f"{stem}|{event}"] = (now + timedelta(hours=24)).isoformat(timespec="seconds")
    path.write_text(json.dumps(w, ensure_ascii=False, indent=1), encoding="utf-8")
    return f"재무 대기 — {w[f'{stem}|{event}']} 뒤 다시"


def call_date(cid, companies=COMPANIES):
    p = companies / cid / "datapack.json"
    if not p.exists():
        return None
    return str((json.loads(p.read_text(encoding="utf-8")).get("call") or {}).get("date") or "")[:10] or None


def latest_event(rep, events):
    """리포트 발행일까지 끝난 콜 중 가장 최근 건 — 발행 뒤의 다음 분기 콜은 대상이 아니다"""
    hits = [e for e in events.values() if (e.get("id") == rep["id"] or str(e.get("ticker") or "").upper() == rep["ticker"].upper())
            and not e["key"].startswith(PT_ONLY) and e["date"] <= rep["date"]]
    return max(hits, key=lambda e: e["date"], default=None)


def reissued(path=DONE):
    if not path.exists():
        return set()
    with path.open(encoding="utf-8", newline="") as f:
        return {(r["stem"], r["event"]) for r in csv.DictReader(f)}


def status(today=None, root=REP, companies=COMPANIES, events_file=EVENTS):
    today = today or datetime.now(KST).date()
    events = json.loads(events_file.read_text(encoding="utf-8")).get("events", {}) if events_file.exists() else {}
    seen, out = reissued(root / "reissue.csv"), []
    for rep in reports(today, root):
        e, cd = latest_event(rep, events), call_date(rep["id"], companies)
        if not e or (cd and cd >= e["date"]):
            continue
        stem = Path(rep["html"]).stem
        if (stem, e["event"]) in seen:
            continue
        out.append({"stem": stem, "json": f"outputs/tenbagger/reports/{stem}.json", "id": rep["id"], "ticker": rep["ticker"], "key": e["key"], "event": e["event"],
                    "call_date": e["date"], "report_call": cd, "kind": "전문 반영", "state": LABEL.get(e["status"], e["status"])})
    out = sorted(out, key=lambda r: r["stem"])
    return out + updates(today, root, events_file)   # 실적 업데이트(2026-11-12) — 콜이 발행 전·후로 나뉘어 전문 반영과 겹치지 않는다


def due(**kw):
    return [r for r in status(**kw) if r["state"] == "재발행"]


def start(stem, delivery=DELIVERY):
    """이미 발행한 리포트를 다시 내도록 상태를 되돌린다. 같은 Artifact·노션 주소를 갱신한다"""
    p = delivery / f"{stem}.json"
    if not p.exists():
        raise SystemExit(f"발행 기록 없음: {stem}")
    st = json.loads(p.read_text(encoding="utf-8"))
    art, nt = (st.get("artifact") or {}).get("url"), (st.get("notion") or {}).get("page")
    st["artifact"] = {"status": "pending", "url": art}
    st["notion"] = {"status": "pending", "page": nt}
    st["reissue"] = {"started": datetime.now(KST).isoformat(timespec="seconds")}
    p.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"artifact_url": art, "notion_page": nt}


def done(stem, event, note, root=REP, delivery=DELIVERY):
    """재발행 기록 절이 있고 텔레그램까지 나간 뒤에만 완료로 친다"""
    d = json.loads((root / f"{stem}.json").read_text(encoding="utf-8"))
    if not any(NOTE_H2 in str(s.get("h2")) for s in d.get("sections") or []):
        raise SystemExit(f"리포트 맨 끝에 '{NOTE_H2}' 절이 없다")
    st = json.loads((delivery / f"{stem}.json").read_text(encoding="utf-8"))
    started, tg = (st.get("reissue") or {}).get("started", ""), st.get("telegram") or {}
    if not tg.get("sent") or not started or tg.get("at", "") < started:
        raise SystemExit("재발행 텔레그램이 나가지 않았다 — publish_tenbagger.py send <json> --reissue 먼저")
    path = root / "reissue.csv"
    new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "stem", "ticker", "event", "note"])
        w.writerow([datetime.now(KST).isoformat(timespec="seconds"), stem, d.get("ticker"), event, note[:300]])
    return "완료"


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--status" in argv:
        print(json.dumps(status(), ensure_ascii=False, indent=1))
    elif "--due" in argv:
        print(json.dumps(due(), ensure_ascii=False, indent=1))
    elif "--start" in argv:
        print(json.dumps(start(argv[argv.index("--start") + 1]), ensure_ascii=False, indent=1))
    elif "--wait-fin" in argv:
        i = argv.index("--wait-fin")
        print(wait_fin(argv[i + 1], argv[i + 2]))
    elif "--done" in argv:
        i = argv.index("--done")
        print(done(argv[i + 1], argv[i + 2], argv[i + 3]))
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
