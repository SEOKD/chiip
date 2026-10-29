"""텔레그램 개인 알림 (BUILD_PROMPT §10.7) — 마스터 개인 대화방으로만.

- 토큰·채팅 id는 D:\\local-only\\secrets\\.env (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
- 키가 없으면 radar/state/outbox.log 에 기록만 한다.
- 공개 채널 게시 기능은 만들지 않는다(P15).
- 발송 전 가드: 금칙어(denylist), 엠바고 표시가 있으면 차단.

- P0·P1 알림은 건별 즉시 발송(2026-10-28 마스터 지시: 브리프 대신 실시간, §21.13) + '⭐ 노션 기록' 버튼.

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


ALERTS = "alerts"  # radar/state/alerts.json — ⭐ 버튼이 가리키는 알림 내용(노션 기록용)


def remember_alert(item, level, what=None, impact=None, card_id=None):
    """알림 1건을 기억하고 콜백용 짧은 ref를 돌려준다(callback_data 64바이트 제한)"""
    import hashlib
    ref = hashlib.sha1(item["item_id"].encode()).hexdigest()[:12]
    st = common.load_state(ALERTS, {})
    st[ref] = {"item_id": item["item_id"], "level": level, "title": item.get("title", ""), "url": item.get("url", ""),
               "what": what, "impact": impact, "card": card_id, "doc_type": item.get("doc_type"),
               "entities": item.get("entities_matched", []), "published_at": item.get("published_at"),
               "publisher": item.get("publisher") or publisher(item), "source_id": item.get("source_id"),
               "sent_at": common.iso(common.now_kst())}
    if len(st) > 3000:
        st = dict(list(st.items())[-3000:])
    common.save_state(ALERTS, st)
    return ref


def send(text, level="P1", ref=None):
    reason = guard(text)
    if reason:
        _log(f"[차단:{reason}] (내용 생략)")
        return False
    if len(text) > MAX_LEN:   # 2026-10-29: 숏 리포트·파이낸싱이 붙은 펄스가 3,800자를 넘으면 뒷부분이 잘렸다 → 문단 단위로 나눠 보낸다
        lim = MAX_LEN - 20   # '(i/n)' 꼬리를 붙여도 한도 안 — 넘으면 다시 나뉘며 끝없이 재귀한다
        parts, cur = [], ""
        for para in text.split("\n"):
            while len(para) > lim:
                if cur:
                    parts.append(cur)
                    cur = ""
                parts.append(para[:lim])
                para = para[lim:]
            if cur and len(cur) + len(para) + 1 > lim:
                parts.append(cur)
                cur = para
            else:
                cur = f"{cur}\n{para}" if cur else para
        if cur:
            parts.append(cur)
        oks = [send(p + f"\n({i}/{len(parts)})", level, ref if i == 1 else None) for i, p in enumerate(parts, 1)]
        return all(oks)
    env = common.load_env()
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        _log(f"[미발송-키없음][{level}] {text}")
        return False
    payload = {"chat_id": chat, "text": text, "disable_web_page_preview": "true"}
    if ref:  # 알림마다 '⭐ 노션 기록' 버튼 — 누르면 radar/telegram_inbox.py가 인텔 아카이브에 기록
        payload["reply_markup"] = json.dumps({"inline_keyboard": [[{"text": "⭐ 노션 기록", "callback_data": f"save:{ref}"}]]})
    data = urllib.parse.urlencode(payload).encode()
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
    if src == "src-jp-disclosure":   # 일본 정보망 — 적시공시 미러·일본 매체(config/jp_watch.yaml publishers), 2026-10-29
        return True, ""
    if item.get("doc_type") in rule.get("brief_only_doc_types", []):
        return False, f"브리프 전용({item.get('doc_type')})"
    if src in rule.get("wire_sources", []):
        return (True, "") if src in rule.get("allowed_wire_sources", []) else (False, "배포처 제한")
    if item.get("doc_type") != "기사":
        return True, ""
    pub = publisher(item)
    allowed = {p.lower() for p in rule.get("allowed_publishers", [])}
    return (True, "") if pub.lower() in allowed else (False, f"매체 제한({pub or '매체 미상'})")


SUB_KO = {"power_infra": "데이터센터·전력 인프라", "semicap": "반도체 장비", "substrate": "반도체 기판·PCB", "networking": "네트워크 장비·칩",
          "software": "소프트웨어", "components": "전자 부품", "hyperscaler": "클라우드(하이퍼스케일러)", "eda_ip": "반도체 설계 도구·IP",
          "accelerator": "AI 가속기·칩", "analog": "아날로그·전력 반도체", "server": "서버 제조", "memory": "메모리 반도체",
          "foundry": "파운드리(반도체 위탁생산)", "conglomerate": "복합 기업", "storage": "스토리지", "ems": "전자제품 위탁생산(EMS)",
          "materials": "반도체 소재", "devices": "전자 기기", "robotics": "로봇", "semis": "반도체", "cooling": "데이터센터 냉각"}
_LINES = {}


def company_line(entity_ids, biz=None):
    """알림 맨 위 '기업:' 1줄(마스터 지시 2026-10-29 — 어떤 사업을 하는 기업인지). config/company_lines.yaml → watchlist
    value_chain_role → 판정 모델의 biz → 감시 목록 sub. 하나도 없으면 None(지어내지 않는다)"""
    if "lines" not in _LINES:
        _LINES["lines"] = (common.load_yaml("config/company_lines.yaml") or {}).get("lines") or {}
        _LINES["wl"] = {r["entity_id"]: (r.get("name"), r.get("value_chain_role")) for r in common.load_watchlist()}
        subs = {}
        for f in ("config/valuation.yaml", "config/earnings_watch.yaml"):
            d = common.load_yaml(f) or {}
            for u in (d.get("universe") or []) + (d.get("extra") or []):
                subs.setdefault(u["id"], (u.get("name"), u.get("sub")))
        for co in (common.load_yaml("config/jp_watch.yaml") or {}).get("companies") or []:   # 일본 정보망 45개사
            subs.setdefault(co["id"], (f"{co['en']}({(co.get('ja') or [''])[0]})", co.get("sub")))
        _LINES["sub"] = subs
    for e in entity_ids or []:
        if _LINES["lines"].get(e):
            return _LINES["lines"][e]
        name, role = _LINES["wl"].get(e, (None, None))
        if role:
            return f"{name} — {role}"
    if biz:
        return biz
    for e in entity_ids or []:
        name, sub = _LINES["sub"].get(e, (None, None))
        if sub:
            return f"{name} — {SUB_KO.get(sub, sub)}"
    return None


def format_item(level, item, what=None, impact=None, card_id=None, biz=None):
    ent = ",".join(item.get("entities_matched", [])) or "-"
    lines = [f"[{level}] {ent} | {item.get('doc_type', '')} | {item.get('detected_at', '')[11:16]}"]
    line = company_line(item.get("entities_matched"), biz)
    if line:
        lines.append(f"기업: {line}")
    lines.append(f"무엇: {what or item['title']}")
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
