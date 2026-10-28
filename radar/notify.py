"""텔레그램 개인 알림 (BUILD_PROMPT §10.7) — 마스터 개인 대화방으로만.

- 토큰·채팅 id는 D:\\local-only\\secrets\\.env (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
- 키가 없으면 radar/state/outbox.log 에 기록만 한다.
- 공개 채널 게시 기능은 만들지 않는다(P15).
- 발송 전 가드: 금칙어(denylist), 엠바고 표시가 있으면 차단.

사용: py radar/notify.py "메시지"        (시험 발송)
      py radar/notify.py --flush         (P1 묶음 발송)
      py radar/notify.py --chat-id       (봇에게 말을 건 개인 대화방 id 찾기 — 토큰은 출력하지 않음)
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

OUTBOX = common.STATE / "outbox.log"
P1_QUEUE = common.STATE / "p1_queue.jsonl"
MAX_LEN = 3800


def _denylist():
    f = common.LOCAL_ONLY / "sealed" / "denylist.txt"
    if not f.exists():
        return []
    return [l.strip().lower() for l in f.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]


def guard(text):
    low = text.lower()
    if any(t in low for t in _denylist()):
        return "금칙어 포함"
    if "[embargo" in low or "엠바고 원문" in text:
        return "엠바고 표시 포함"
    return None


def send(text, level="P1"):
    reason = guard(text)
    if reason:
        _log(f"[차단:{reason}] (내용 생략)")
        return False
    env = common.load_env()
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        _log(f"[미발송-키없음][{level}] {text}")
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:MAX_LEN],
                                   "disable_web_page_preview": "true"}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=20) as r:
            ok = json.loads(r.read()).get("ok", False)
    except Exception as exc:  # 네트워크 오류 — 토큰이 섞일 수 있는 URL은 기록하지 않음
        _log(f"[발송실패][{level}] {type(exc).__name__}")
        common.record_health("telegram", False, type(exc).__name__)
        return False
    common.record_health("telegram", ok, None if ok else "ok=false")
    _log(f"[발송{'됨' if ok else '실패'}][{level}] {text[:80]}")
    return ok


def _log(line):
    OUTBOX.parent.mkdir(parents=True, exist_ok=True)
    with OUTBOX.open("a", encoding="utf-8") as f:
        f.write(f"{common.iso(common.now_kst())} {line}\n")


def publisher(item):
    """기사 매체명: RSS <source> 값, 없으면 Google News 제목 끝 ' - 매체명'"""
    if item.get("publisher"):
        return item["publisher"].strip()
    title = item.get("title", "")
    return title.rsplit(" - ", 1)[1].strip() if " - " in title else ""


def telegram_allowed(item):
    """텔레그램 매체 제한(config/alert_rules.yaml telegram_filter). (허용 여부, 사유)"""
    rule = (common.load_yaml("config/alert_rules.yaml") or {}).get("telegram_filter")
    if not rule:
        return True, ""
    src = item.get("source_id", "")
    if item.get("doc_type") in rule.get("brief_only_doc_types", []):
        return False, f"브리프 전용({item.get('doc_type')})"
    if src in rule.get("wire_sources", []):
        return (True, "") if src in rule.get("allowed_wire_sources", []) else (False, "배포처 제한")
    if item.get("doc_type") != "기사":
        return True, ""
    pub = publisher(item)
    allowed = {p.lower() for p in rule.get("allowed_publishers", [])}
    return (True, "") if pub.lower() in allowed else (False, f"매체 제한({pub or '매체 미상'})")


def format_item(level, item, what=None, impact=None, card_id=None):
    ent = ",".join(item.get("entities_matched", [])) or "-"
    lines = [f"[{level}] {ent} | {item.get('doc_type', '')} | {item.get('detected_at', '')[11:16]}",
             f"무엇: {what or item['title']}"]
    if impact:
        lines.append(f"영향: {impact} (1차 판정)")
    lines.append(item["url"])
    if card_id:
        lines.append(f"카드: {card_id}")
    return "\n".join(lines)


def queue_p1(text):
    P1_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with P1_QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": common.iso(common.now_kst()), "text": text}, ensure_ascii=False) + "\n")


def flush_p1(min_age_min=60, force=False):
    if not P1_QUEUE.exists():
        return 0
    rows = [json.loads(l) for l in P1_QUEUE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not rows:
        return 0
    from datetime import datetime, timedelta
    oldest = datetime.fromisoformat(rows[0]["at"])
    if not force and common.now_kst() - oldest < timedelta(minutes=min_age_min):
        return 0
    body = f"[P1 묶음 {len(rows)}건]\n\n" + "\n\n".join(r["text"] for r in rows)
    send(body, "P1")
    P1_QUEUE.write_text("", encoding="utf-8")
    return len(rows)


def find_chat_ids():
    token = common.load_env().get("TELEGRAM_BOT_TOKEN")
    if not token:
        return "TELEGRAM_BOT_TOKEN 이 비어 있습니다"
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20) as r:
            res = json.loads(r.read()).get("result", [])
    except Exception as exc:  # 토큰이 섞일 수 있는 URL은 출력하지 않음
        return f"조회 실패: {type(exc).__name__} (토큰 확인)"
    chats = {}
    for u in res:
        c = (u.get("message") or u.get("edited_message") or {}).get("chat", {})
        if c.get("type") == "private":
            chats[c["id"]] = c.get("first_name", "")
    if not chats:
        return "대화 기록 없음 — 텔레그램에서 봇에게 아무 말이나 보낸 뒤 다시 실행"
    return "\n".join(f"TELEGRAM_CHAT_ID={cid}   ({name})" for cid, name in chats.items())


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--flush":
        print(flush_p1(force=True))
    elif len(sys.argv) > 1 and sys.argv[1] == "--chat-id":
        print(find_chat_ids())
    else:
        print(send(" ".join(sys.argv[1:]) or "치입 알림 시험", "TEST"))
