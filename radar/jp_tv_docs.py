"""일본 어닝콜 전사 확인 (마스터 지시 2026-11-02 "지난 3주 동안 실적을 발표한 회사 중에서 Q&A Summary나 어닝콜 스크립트를 올린 기업이 있는지 다시 점검하고
있다면 어닝을 공유하고 어닝콜 스크립트를 가져오는 파이프라인 시스템을 강화하라")

TradingView 문서 도구(Quartr 제공)에 일본 어닝콜 전사·Q&A·요약이 있다. E-IR 때문에 회사 자료실을 못 읽던 키옥시아도 나온다.
결정론 스크립트는 TradingView MCP를 부를 수 없어 transcript_watch.py처럼 '대상 목록 → 모델 호출 → 결과 넣기'로 돈다.
  대상: 지난 21일 적시공시 미러에 결산 제목이 뜬 일본 감시 회사(run_hourly가 한 시간마다 갱신)
  순서: 보유·알파 5+·노션 Stocks > 알파 산정 종목 > 나머지
  주기: 하루 1회 3종목까지(2026-11-21, 이전 20분). 없으면 6·12·24·48·72시간 뒤 다시 보고, 발표 후 10일이 지나면 만료
호출 상한(2026-11-02 사고): 66종목을 한 번에 조회해 TradingView가 1분 정지하고 '계속하면 하루 정지'를 경고했다. 한 메시지에 호출 하나, 회차당 MAX_PER_RUN을 넘기지 않는다.
사용: py radar/jp_tv_docs.py              # 이번 회차 대상(JSON)
      py radar/jp_tv_docs.py --put <파일>  # {"TSE:6857": get_documents 출력} → 새로 찾은 전사
      py radar/jp_tv_docs.py --done <id>   # 정리를 마친 건
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

STATE = "jp_tv_docs"
SOURCE = "src-jp-disclosure"
RESULT_RE = re.compile(r"決算|四半期")
LOOK_DAYS = 21
WAIT_DAYS = 10
EVERY_MIN = 1440   # 2026-11-21 마스터 지시 'TradingView 한도 조정 세 가지 적용' — 20분 → 하루 1회(11/20 TradingView 호출 56건 중 Pulse 43건이 이 조회)
MAX_PER_RUN = 3
BACKOFF_H = (6, 12, 24, 48, 72)
# 공식 IR 1순위(2026-11-22 마스터 지시 "일본 종목 어닝콜 전사 확인은 일본 상장 기업의 공식 IR 채널을 참조하는 걸 1순위로") —
# 회사 IR(radar/pollers/jp_ir_qa.py·jp_ir_docs.py)이 결산 뒤 질의응답·스피치·전사를 올리면 TradingView를 부르지 않는다('ir'로 닫는다).
# IR을 읽을 수 있는 회사는 결산 공시 뒤 IR_GRACE_BD 영업일을 기다렸다가 그래도 없을 때만 TradingView(대체 경로)로 간다.
# IR을 못 읽는 회사(robots로 막힌 외부 대행·E-IR·Xj-Storage·IR Pocket, 또는 IR 설정 없음)는 바로 TradingView.
# 11/09~21 사례: TOWA는 11/10 IR에 질의응답 PDF가 올라왔는데도 TradingView를 4번 불렀다 만료.
IR_GRACE_BD = 3
IR_DOC_RE = re.compile(r"質疑|Ｑ＆Ａ|Q\s?&\s?A|スピーチ|書き?起こし|ログ|transcript|script", re.I)
IR_UNREADABLE = ("E-IR", "Xj-Storage", "IR Pocket", "봇 차단")


def ir_found(now, look_days=None):
    """{id: {"date", "url", "title"}} — 공식 IR에서 받은 질의응답·스피치·전사 중 가장 최근(레이더 수집함 src-jp-ir-qa·src-jp-ir-docs)"""
    out = {}
    for k in range((look_days or LOOK_DAYS) + 1):
        day = common.INBOX / (now - timedelta(days=k)).strftime("%Y%m%d")
        for f in day.glob("*.json") if day.exists() else []:
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            src, title = it.get("source_id"), str(it.get("title") or "")
            if src != "src-jp-ir-qa" and not (src == "src-jp-ir-docs" and IR_DOC_RE.search(title)):
                continue
            d = str(it.get("published_at"))[:10]
            for cid in it.get("entities_matched") or []:
                if d > out.get(cid, {}).get("date", ""):
                    out[cid] = {"date": d, "url": it.get("url"), "title": title}
    return out


def ir_readable(cid):
    """공식 IR 자료실을 자동으로 읽을 수 있는 회사인가 — 설정이 있고, robots로 막히지 않았고, 자바스크립트·대행 목록이 아닌 곳"""
    c = ((common.load_yaml("config/jp_ir.yaml") or {}).get("companies") or {}).get(cid)
    if not c or cid in ir_blocked() or any(a in str(c.get("access") or "") for a in IR_UNREADABLE):
        return False
    # 실제로 자료실·IR 페이지를 찾은 회사만(설정만 있고 탐색이 못 찾은 34곳은 기다려도 IR에서 안 나온다 — 2026-11-22 점검)
    qa = (common.load_state("jp_ir_qa", {}).get("companies") or {}).get(cid) or {}
    docs = (common.load_state("jp_ir_docs", {}).get("companies") or {}).get(cid) or {}
    return bool(qa.get("pages") or docs.get("pages") or c.get("doc_pages") or c.get("ir_pages"))


def _after_bd(day, n):
    """day(YYYY-MM-DD) 뒤 n 영업일(주말·도쿄증권거래소 휴장일 제외)"""
    hol = set(str(x) for x in (common.load_yaml("config/jp_ir.yaml") or {}).get("holidays") or [])
    d = datetime.fromisoformat(day)
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.date().isoformat() not in hol:
            n -= 1
    return d


def companies():
    """id → 종목코드(일본 IR 감시 회사)"""
    ir = (common.load_yaml("config/jp_ir.yaml") or {}).get("companies") or {}
    watch = {c["id"]: c for c in (common.load_yaml("config/jp_watch.yaml") or {}).get("companies") or []}
    return {i: watch[i] for i in ir if watch.get(i, {}).get("code")}


def ir_blocked():
    """회사 IR Q&A가 외부 대행 사이트 robots로 막힌 회사(radar/pollers/jp_ir_qa.py가 기록) — Q&A 경로가 TradingView뿐이라 먼저 본다(2026-11-09 도쿄일렉트론·국제전기)"""
    st = common.load_state("jp_ir_qa", {}).get("companies") or {}
    return {k for k, v in st.items() if v.get("blocked_hosts")}


def tier(cid):
    from pollers import gate
    if cid in gate.portfolio_ids() or cid in gate.extra_focus() or cid in ir_blocked():
        return 0
    alpha = common.ROOT / "knowledge" / "models" / "alpha" / "latest.json"
    rows = json.loads(alpha.read_text(encoding="utf-8")).get("rows") or {} if alpha.exists() else {}
    return 1 if cid in rows else 2


def results_seen(now):
    """{id: 가장 최근 결산 공시일} — 지난 LOOK_DAYS 수집함"""
    out = {}
    for k in range(LOOK_DAYS + 1):
        day = common.INBOX / (now - timedelta(days=k)).strftime("%Y%m%d")
        for f in day.glob("*.json") if day.exists() else []:
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if it.get("source_id") != SOURCE or not RESULT_RE.search(it.get("title") or ""):
                continue
            for cid in it.get("entities_matched") or []:
                out[cid] = max(out.get(cid, ""), str(it.get("published_at"))[:10])
    return out


def refresh(st, now, seen=None):
    """새 결산 공시를 대상에 넣고 기한이 지난 건은 만료로"""
    names, rows = companies(), st.setdefault("targets", {})
    for cid, day in (results_seen(now) if seen is None else seen).items():
        c, cur = names.get(cid), rows.get(cid)
        if c and (not cur or day > cur["date"] and cur["status"] != "wait"):
            readable = ir_readable(cid)
            first = max(now, _after_bd(day, IR_GRACE_BD).replace(hour=9, tzinfo=now.tzinfo)) if readable else now   # 공식 IR 1순위 — IR을 읽을 수 있으면 유예 뒤에만 TradingView
            rows[cid] = {"id": cid, "symbol": f"TSE:{c['code']}", "code": c["code"], "name": c.get("en") or cid, "date": day, "tier": tier(cid),
                         "status": "wait", "tries": 0, "next_at": common.iso(first), "route": "ir_first" if readable else "tv_only"}
    found = ir_found(now)
    for r in rows.values():   # 공식 IR에 결산 뒤 질의응답·전사가 올라왔으면 TradingView를 부르지 않는다
        hit = found.get(r["id"])
        if r["status"] == "wait" and hit and hit["date"] >= (datetime.fromisoformat(r["date"]) - timedelta(days=1)).date().isoformat():
            r.update(status="ir", ir_doc=hit, ir_at=common.iso(now))
    cut = (now - timedelta(days=WAIT_DAYS)).date().isoformat()
    for r in rows.values():
        if r["status"] == "wait" and r["date"] < cut:
            r["status"] = "expired"
    return st


def batch(st, now):
    ready = [r for r in st.get("targets", {}).values() if r["status"] == "wait" and datetime.fromisoformat(r["next_at"]) <= now]
    return sorted(ready, key=lambda r: (r["tier"], r["date"]))[:MAX_PER_RUN]


def status(now=None, st=None):
    """펄스 관문용 — 확인할 종목이 있고 마지막 확인 뒤 EVERY_MIN이 지났거나, 정리할 전사가 남았으면 due"""
    now = now or common.now_kst()
    st = st if st is not None else common.load_state(STATE, {})
    last = st.get("last_check")
    ok = not last or datetime.fromisoformat(last) + timedelta(minutes=EVERY_MIN) <= now
    check = [{"id": r["id"], "symbol": r["symbol"], "date": r["date"]} for r in batch(st, now)] if ok else []
    found = [r for r in st.get("targets", {}).values() if r["status"] == "found"]
    return {"due": bool(check or found), "check": check, "found": sorted(found, key=lambda r: (r["tier"], r["date"]))}


def views(doc):
    v = {x["type"]: x["id"] for x in doc.get("views") or []}
    return {"title": doc.get("title"), "qa": "Q&A" in str(doc.get("title")), "reported": doc.get("reported"), "transcript": v.get("transcript"), "summary": v.get("summary")}


def record(r, data, now):
    """get_documents 출력 한 건을 대상에 반영한다"""
    start = (datetime.fromisoformat(r["date"]) - timedelta(days=2)).timestamp()
    docs = [views(d) for d in data.get("items") or [] if (d.get("category") or {}).get("id") == "call_transcript" and (d.get("reported") or 0) >= start]
    r["tries"] += 1
    if docs:
        r.update(status="found", docs=docs, found_at=common.iso(now))
    else:
        r["next_at"] = common.iso(now + timedelta(hours=BACKOFF_H[min(r["tries"] - 1, len(BACKOFF_H) - 1)]))


def put(path, now=None):
    now = now or common.now_kst()
    text = Path(path).read_text(encoding="utf-8")
    data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    st = common.load_state(STATE, {})
    by = {r["symbol"]: r for r in st.get("targets", {}).values()}
    for sym, res in data.items():
        if sym in by and by[sym]["status"] == "wait":
            record(by[sym], res, now)
    st["last_check"] = common.iso(now)
    common.save_state(STATE, st)
    return status(now, st)["found"]


def done(cid, now=None):
    st = common.load_state(STATE, {})
    r = st.get("targets", {}).get(cid)
    if not r:
        return "해당 건 없음"
    r.update(status="done", done_at=common.iso(now or common.now_kst()))
    common.save_state(STATE, st)
    return "완료"


def run():
    """run_hourly용 — 대상 목록 갱신. TradingView는 부르지 않는다"""
    st = refresh(common.load_state(STATE, {}), common.now_kst())
    common.save_state(STATE, st)
    return len(st["targets"]), 0


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--put" in argv:
        print(json.dumps(put(argv[argv.index("--put") + 1]), ensure_ascii=False, indent=1))
    elif "--done" in argv:
        print(done(argv[argv.index("--done") + 1]))
    else:
        print(json.dumps(status(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
