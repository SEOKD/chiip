"""어닝콜 전문 신규 게재 감시 (마스터 지시 2026-10-30 "어닝 콜이 막 끝나면 Fiscal.ai에 바로 올라오지 않고 스크립트가 올라오는 데 딜레이가 있다.
네가 탐지하는 종목군 중에 Fiscal.ai에 어닝콜 스크립트가 신규로 올라오는 게 있으면 이를 정리하도록 해라")

결정론 스크립트는 Fiscal.ai MCP를 직접 부를 수 없다(ADR-012) — 그래서 실적 일정처럼 '코드 만들기 → 모델이 execute_code → 결과 넣기'로 돈다.
  대상: Fiscal 실적 일정(knowledge/models/earnings/fiscal_calendar.json — 감시 종목 전체, 어제~)에서 콜이 끝난(예정 시각 + 1시간이 지난) 발표를
        상태 파일에 쌓아 두고(일정 파일은 매일 어제부터 새로 받으므로 지난 건은 여기서 보관), 발표 후 10일까지 전문을 기다린다.
  주기: 대기 건이 있을 때만, 마지막 확인 뒤 20분이 지나면 펄스(radar/pulse.py)가 'transcripts.due'로 회차를 연다 — 모델 폴링을 대기 건으로 묶어 둔다.
  우선순위: 보유 종목 > 레이더 테마·노션 Stocks·알파 5+ > 나머지. 한 회차에 정리는 2건까지(나머지는 다음 회차).
사용: py radar/transcript_watch.py                  # 상태 요약(JSON)
      py radar/transcript_watch.py --code           # 확인할 [{key, event}]를 채운 execute_code 본문(최대 36건)
      py radar/transcript_watch.py --put <파일>      # execute_code 출력 → 새로 올라온 전문 목록(정리 대상, 우선순위 순)
      py radar/transcript_watch.py --done <key> <event> [--no-feed <이유>]   # 정리를 마친 전문(④ 인사이트 피드 파일이 있어야 완료)
      py radar/transcript_watch.py --await <key> <event>  # 보도자료로 ②를 먼저 보낸 실적 — 전문이 오면 ②·③을 콜 기준으로 다시
정리 범위: 보유·레이더 테마·노션 Stocks·알파 5+(tier 0·1)는 Dean's Ticker 3단(① 미발송이면 ①부터), 나머지(tier 2)는 ② 뉴팩트 한 통.
  + 어느 범위든 ④ 인사이트 피드 한 통(마스터 지시 2026-10-30 "뒤늦게 올라오면 뉴팩트 정리와 함께 인사이트 피드도") — 숫자는
  scripts/insight/call_feed.py(발표 반응 AR·β·게재까지 표류·Q&A 비교), 양식은 knowledge/methods/earnings_format.md ④. --done은 ④ 파일이 있어야 완료로 친다.
  이미 콜 기준 ②를 보낸 실적(②·③ 파일이 있고 --await 표시가 없음)은 '이미 정리'로 넘긴다.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

STATE = "transcripts"
CAL = common.ROOT / "knowledge" / "models" / "earnings" / "fiscal_calendar.json"
TPL = common.ROOT / "scripts" / "fiscal" / "templates" / "transcript_check.js"
EARN = common.ROOT / "outputs" / "article" / "earnings"
WAIT_DAYS = 10        # 발표 뒤 이 기간까지 전문을 기다린다
CALL_LAG_H = 1        # 예정 시각 + 이 시간이 지나야 콜이 끝난 것으로 본다
EVERY_MIN = 20        # 대기 건이 있을 때 확인 간격
MAX_CHECK = 36        # 한 번에 확인하는 건수(execute_code 60초 안)


def event_key(period):
    """'Q1 2027' → 'q1-2027'(Fiscal 이벤트 키). 연간 실적('FY 2026'·'Q4')은 q4"""
    m = re.search(r"Q([1-4])\D*(\d{4})", str(period or ""), re.I)
    if m:
        return f"q{m.group(1)}-{m.group(2)}"
    m = re.search(r"(?:FY|H2|Annual)\D*(\d{4})", str(period or ""), re.I)
    return f"q4-{m.group(1)}" if m else None


def _utc(e):
    s = e.get("utc")
    if s:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    d = datetime.fromisoformat(e["date"]).replace(tzinfo=timezone.utc)
    return d + timedelta(hours=23)   # 시각 미정이면 그날 끝


def _ids():
    """회사 키 → 감시 id(우선순위 계산용). 실적 일정 모듈의 대응표를 그대로 쓴다"""
    from markets import earnings_calendar as ec
    us, keys = ec.fiscal_targets(ec.watch())
    out = dict(keys)
    for t, i in us.items():
        out.setdefault(t, i)
    return out


def _tier(cid):
    from pollers import gate
    if cid in gate.portfolio_ids():
        return 0
    return 1 if cid in gate.extra_focus() else 2


def refresh(st, now, cal=None):
    """일정 파일의 발표 건을 상태에 쌓고, 기한이 지난 대기 건은 '만료'로"""
    if cal is None:
        cal = json.loads(CAL.read_text(encoding="utf-8")) if CAL.exists() else {"events": []}
    ev = st.setdefault("events", {})
    idmap = None
    for e in cal.get("events") or []:
        k = event_key(e.get("period"))
        if not k or not e.get("key"):
            continue
        rid = f"{e['key']}|{k}"
        if rid in ev:
            continue
        if idmap is None:
            try:
                idmap = _ids()
            except Exception:
                idmap = {}
        cid = idmap.get(e["key"]) or idmap.get(e.get("ticker") or "")
        ev[rid] = {"key": e["key"], "event": k, "ticker": e.get("ticker"), "name": e.get("name"), "date": e["date"],
                   "utc": _utc(e).isoformat(), "id": cid, "status": "wait"}
    cut = now - timedelta(days=WAIT_DAYS)
    for r in ev.values():
        if r["status"] == "wait" and datetime.fromisoformat(r["utc"]) < cut:
            r["status"] = "expired"
    # 오래된 기록은 정리(60일)
    old = (now - timedelta(days=60)).isoformat()
    st["events"] = {k: v for k, v in ev.items() if v["utc"] >= old}
    return st


def pending(st, now):
    """콜이 끝났고 아직 전문이 없는 건 — 우선순위·발표일 순"""
    ready = [r for r in st.get("events", {}).values() if r["status"] == "wait" and datetime.fromisoformat(r["utc"]) + timedelta(hours=CALL_LAG_H) <= now]
    for r in ready:
        r.setdefault("tier", _tier(r.get("id")) if r.get("id") else 2)
    return sorted(ready, key=lambda r: (r["tier"], r["utc"]))


def to_summarize(st):
    return sorted([r for r in st.get("events", {}).values() if r["status"] == "found"], key=lambda r: (r.get("tier", 2), r["utc"]))


def due(now=None, st=None):
    """펄스 관문용 — 확인할 대기 건이 있고 마지막 확인 뒤 EVERY_MIN이 지났거나, 정리할 전문이 남았으면 True"""
    now = now or datetime.now(timezone.utc)
    st = refresh(st if st is not None else common.load_state(STATE, {}), now)
    last = st.get("last_check")
    waiting = pending(st, now)
    check = bool(waiting) and (not last or datetime.fromisoformat(last) + timedelta(minutes=EVERY_MIN) <= now)
    return {"due": check or bool(to_summarize(st)), "check": check, "waiting": len(waiting), "to_summarize": len(to_summarize(st))}


def _rel(p):
    return p.relative_to(common.ROOT).as_posix() if p.is_relative_to(common.ROOT) else str(p)


def feed_path(r, now=None):
    """④ 인사이트 피드 파일 — 전문을 찾은 날(KST) 이름"""
    at = datetime.fromisoformat(r["found_at"]) if r.get("found_at") else (now or datetime.now(timezone.utc))
    day = (at + timedelta(hours=9)).strftime("%Y%m%d")
    return EARN / f"{day}_{(r.get('ticker') or '').upper()}_4.txt"


def earnings_files(r):
    """이미 보낸 Dean's Ticker 파일(발표일·다음 날·전문 발견일 KST 파일명, ④ = 인사이트 피드)"""
    t = (r.get("ticker") or "").upper()
    d = datetime.fromisoformat(r["date"])
    days = [d, d + timedelta(days=1)]
    if r.get("found_at"):
        days.append(datetime.fromisoformat(r["found_at"]) + timedelta(hours=9))
    out = {}
    for day in days:
        for n in (1, 2, 3, 4):
            p = EARN / f"{day.strftime('%Y%m%d')}_{t}_{n}.txt"
            if p.exists():
                out[n] = _rel(p)
    return out


def code(now=None):
    now = now or datetime.now(timezone.utc)
    st = refresh(common.load_state(STATE, {}), now)
    items = [{"key": r["key"], "event": r["event"]} for r in pending(st, now)[:MAX_CHECK]]
    common.save_state(STATE, st)
    return TPL.read_text(encoding="utf-8").replace("__ITEMS__", json.dumps(items)), len(items)


def put(path, now=None):
    now = now or datetime.now(timezone.utc)
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    st = refresh(common.load_state(STATE, {}), now)
    ev = st["events"]
    for f in data.get("found") or []:
        r = ev.get(f"{f['key']}|{f['event']}")
        if r and r["status"] == "wait":
            r.setdefault("tier", _tier(r.get("id")) if r.get("id") else 2)
            r.update({"status": "found", "found_at": now.isoformat(), "paragraphs": f.get("paragraphs"), "qa": f.get("qa"),
                      "lag_h": round((now - datetime.fromisoformat(r["utc"])).total_seconds() / 3600, 1)})
            files = earnings_files(r)
            if 2 in files and 3 in files and not r.get("await"):   # 콜 기준 ②·③을 이미 보냈다
                r.update({"status": "done", "done_at": now.isoformat(), "note": "이미 정리(②·③ 파일 있음)"})
    st["last_check"] = now.isoformat()
    st["last_errors"] = (data.get("errors") or [])[:10]
    common.save_state(STATE, st)
    return [dict(r, files=earnings_files(r), scope="3단" if r.get("tier", 2) < 2 else "② 뉴팩트",
                 feed={"file": _rel(feed_path(r)), "code": f"py scripts/insight/call_feed.py code {r['key']} {r['event']}"})
            for r in to_summarize(st)]


def done(key, event, no_feed=None, now=None):
    """정리 완료 — ④ 인사이트 피드 파일이 없으면 완료로 치지 않는다(다음 회차가 다시 잡는다). 피드를 못 쓰는 사유가 있으면 no_feed로 남긴다"""
    st = common.load_state(STATE, {})
    r = st.get("events", {}).get(f"{key}|{event}")
    if not r:
        return "해당 건 없음"
    if 4 not in earnings_files(r) and not no_feed:
        return f"미완료 — 인사이트 피드 파일 없음({_rel(feed_path(r))}). 보낸 뒤 다시, 못 쓰면 --no-feed <이유>"
    r.update({"status": "done", "done_at": (now or datetime.now(timezone.utc)).isoformat()})
    if no_feed:
        r["no_feed"] = no_feed
    common.save_state(STATE, st)
    return "완료"


def mark_await(key, event, now=None):
    """보도자료로 ②를 먼저 보낸 실적 — 전문이 오면 ②·③을 콜 기준으로 다시 쓴다(earnings_format.md)"""
    now = now or datetime.now(timezone.utc)
    st = refresh(common.load_state(STATE, {}), now)
    r = st["events"].get(f"{key}|{event}")
    if not r:
        return False
    r["await"] = True
    common.save_state(STATE, st)
    return True


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--code" in argv:
        body, n = code()
        print(body)
        print(f"// 확인 대상 {n}건", file=sys.stderr)
        return 0
    if "--put" in argv:
        print(json.dumps(put(argv[argv.index("--put") + 1]), ensure_ascii=False, indent=1))
        return 0
    if "--await" in argv:
        i = argv.index("--await")
        print("표시" if mark_await(argv[i + 1], argv[i + 2]) else "해당 건 없음(일정에 없는 실적)")
        return 0
    if "--done" in argv:
        i = argv.index("--done")
        nf = " ".join(argv[argv.index("--no-feed") + 1:]) if "--no-feed" in argv else None
        print(done(argv[i + 1], argv[i + 2], nf))
        return 0
    print(json.dumps(due(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
