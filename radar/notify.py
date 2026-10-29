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
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
from units import money_units  # noqa: E402

OUTBOX = common.STATE / "outbox.log"
P1_QUEUE = common.STATE / "p1_queue.jsonl"
MAX_LEN = 3800
BRAND = ("치입", "Chiip")   # 마스터 지시 2026-10-29: 텔레그램·GitHub 보고에는 '치입' 대신 'Chiip'으로 표기


LABELS = [   # 텔레그램 기능 이름은 영어로(마스터 지시 2026-10-29 "Chiip 펄스를 Chiip Pulse로, 나머지도 영어로") — 긴 이름부터
    ("Chiip 포트폴리오 데일리", "Chiip Portfolio Daily"), ("Chiip 텐배거 리포트", "Chiip Ten-bagger Report"), ("Chiip 리포트 게시", "Chiip Report"),
    ("Chiip 뉴스 요약", "Chiip News Digest"), ("Chiip 숏 리포트", "Chiip Short Report"), ("Chiip 실적 일정", "Chiip Earnings Calendar"),
    ("Chiip 기사 소재", "Chiip Article Pitch"), ("Chiip 인사이트 검토", "Chiip Insight Review"), ("Chiip 알파 레이더", "Chiip Alpha Radar"),
    ("Chiip 발굴", "Chiip Ten-bagger Discovery"), ("Chiip 포트폴리오", "Chiip Portfolio"), ("Chiip 텐배거", "Chiip Ten-bagger"), ("Chiip 펄스", "Chiip Pulse"),
    ("Chiip 포커스", "Chiip Focus"), ("Chiip 알림", "Chiip Alerts"), ("Chiip 판단", "Chiip View"), ("Chiip 프로바이저", "Chiip Proviser"),
    ("· 늦은 보고", "· Late"), ("· 개정판", "· Revised"), (" 정정]", " Correction]")]
LEVEL_TAG_RE = re.compile(r"\[P[0-3](?:[-·][^\]]{0,12})?\]\s?")   # 내부 등급 코드 — 마스터에게 드러내지 않는다(2026-10-29 지시)


LEVEL_WORD_RE = re.compile(r"(?<![\w/.=-])P[0-3](?![\w/.=-])(\s?·\s?|\s)?")   # 문장 속 'P0 · '·'P1 ' 등


def brand(text):
    """발송 직전 표기 통일 — 예약 작업·스크립트가 어떤 머리말을 쓰든 텔레그램에는 'Chiip'으로, 등급 코드(P0~P3)는 빼고 나간다"""
    text = re.sub(r"(?m)^[ \t]*보강 적용:.*(\n|$)", "", (text or "").replace(*BRAND))   # 프로바이저 번호는 기록 파일에만(P-20261029-03)
    # 회사 설명 줄의 '모델:'·'성장:'·'내러티브:' 머리말은 빼고 내용만(마스터 지시 2026-10-30)
    text = re.sub(r"(?m)^(☞\s*)?(?:비즈니스\s*)?(?:모델|성장(?:\s*동력)?|내러티브)\s*[:：]\s*", r"\1", text)
    # 펄스·포트폴리오 근거 줄 머리말('**판단**', '· 숫자 —' 등)도 빼고 내용만(마스터 지시 2026-10-30)
    text = re.sub(r"(?m)^\*\*판단\*\*\s*(.+)$", r"**\1**", text)   # 판단 문장은 머리말 없이 굵게
    text = re.sub(r"(?m)^판단\s+(?=\S)", "", text)
    text = re.sub(r"(?m)^(·\s*)(?:숫자|가격|파급|반대|다음|야마|보도 확인|주장|핵심|밸류|수급|조건|참여자|직전 대비|함의|단계|점유|AI 수요|바뀐 말|질문 초점)\s*[—–-]\s*", r"\1", text)
    for ko, en in LABELS:
        text = text.replace(ko, en)
    return money_units(LEVEL_WORD_RE.sub("", LEVEL_TAG_RE.sub("", text)))   # 금액 $25B·$M·$T(마스터 지시 2026-10-29, radar/units.py)


LINK_RE = re.compile(r"\[([^\]\n]{1,80})\]\((https?://[^\s)]+)\)")


def md_to_html(text):
    """펄스 양식용 가벼운 표기 → 텔레그램 HTML(2026-10-29 마스터 지시 '가독성'). **굵게**와 [이름](주소)만 쓰고 나머지는 이스케이프 —
    긴 SEC 주소를 이름 뒤로 숨긴다. 태그는 한 줄 안에서 닫히므로 문단 단위 분할에도 깨지지 않는다"""
    out, pos = [], 0
    for m in LINK_RE.finditer(text or ""):
        out.append(html.escape(text[pos:m.start()], quote=False))
        out.append(f'<a href="{html.escape(m.group(2), quote=True)}">{html.escape(m.group(1), quote=False)}</a>')
        pos = m.end()
    out.append(html.escape((text or "")[pos:], quote=False))
    return re.sub(r"\*\*([^*\n]{1,300})\*\*", r"<b>\1</b>", "".join(out))


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


def send_document(path, caption="", level="REPORT"):
    """파일(HTML 리포트 등)을 마스터 개인 텔레그램으로 보낸다 — 2026-10-29 텐배거 일일 리포트. 본문 검사(guard)는 캡션과 파일 내용 모두에"""
    path = Path(path)
    caption = brand(caption)
    body_text = path.read_text(encoding="utf-8", errors="ignore") if path.suffix in (".html", ".md", ".txt") else ""
    reason = guard(caption) or (guard(body_text) if body_text else None)
    if reason:
        _log(f"[차단:{reason}] 파일 {path.name}")
        return False
    env = common.load_env()
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        _log(f"[미발송-키없음][{level}] 파일 {path.name}")
        return False
    import uuid
    bnd = uuid.uuid4().hex
    parts = []
    for k, v in (("chat_id", chat), ("caption", caption[:1000])):
        parts.append(f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
    parts.append(f'--{bnd}\r\nContent-Disposition: form-data; name="document"; filename="{path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode("utf-8")
                 + path.read_bytes() + b"\r\n")
    parts.append(f"--{bnd}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendDocument", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={bnd}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            ok = json.loads(r.read()).get("ok", False)
    except Exception as exc:   # 토큰이 섞일 수 있는 URL은 기록하지 않음
        _log(f"[발송실패][{level}] 파일 {path.name} {type(exc).__name__}")
        return False
    _log(f"[발송{'됨' if ok else '실패'}][{level}] 파일 {path.name} · {caption[:60]}")
    return ok


def send(text, level="P1", ref=None, html_mode=False, md=False):
    text = brand(text)
    if md:   # 펄스·포트폴리오 양식 — **굵게**·[이름](주소) → HTML
        text, html_mode = md_to_html(text), True
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
        oks = [send(p + f"\n({i}/{len(parts)})", level, ref if i == 1 else None, html_mode) for i, p in enumerate(parts, 1)]
        return all(oks)
    env = common.load_env()
    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        _log(f"[미발송-키없음][{level}] {text}")
        return False
    payload = {"chat_id": chat, "text": text, "disable_web_page_preview": "true"}
    if html_mode:   # 기사 제목에 링크를 숨겨 한 줄 양식을 지킨다
        payload["parse_mode"] = "HTML"
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
    paras = f" ¶{text.count(chr(10) * 2) + 1}" if level in ("P0", "P1") else ""   # 알림 3문단 양식 확인용(머리줄·☞·•)
    _log(f"[발송{'됨' if ok else '실패'}][{level}]{paras} {text[:80]}")
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
          "materials": "반도체 소재", "devices": "전자 기기", "robotics": "로봇", "semis": "반도체", "cooling": "데이터센터 냉각", "defense": "방위"}
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
        _LINES["def"] = {c["id"]: c["biz"] for c in common.defense_companies() if c.get("biz")}   # 방위 섹터 지도
    for e in entity_ids or []:
        if _LINES["lines"].get(e):
            return _LINES["lines"][e]
        if _LINES["def"].get(e):
            return _LINES["def"][e]
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


def _tickers():
    """entity_id → (이름, 종목코드). 보유 종목 → 감시 목록 → 밸류에이션 유니버스 → 어닝 감시 확장 → 일본 정보망 순"""
    if "tk" not in _LINES:
        out = {}
        for h in (common.load_yaml("config/portfolio.yaml") or {}).get("holdings") or []:
            out.setdefault(h.get("id"), (h.get("name"), h.get("ticker")))
        for r in common.load_watchlist():
            out.setdefault(r["entity_id"], (re.sub(r"\s*\(.*?\)", "", r.get("name") or ""), r.get("ticker")))
        for f in ("config/valuation.yaml", "config/earnings_watch.yaml"):
            d = common.load_yaml(f) or {}
            for u in (d.get("universe") or []) + (d.get("extra") or []):
                code = str(u.get("code") or u.get("ticker") or "")
                out.setdefault(u["id"], (u.get("name"), re.sub(r"\.(US|KO|KQ|T|TW|HK)$", "", code) or None))
        for co in (common.load_yaml("config/jp_watch.yaml") or {}).get("companies") or []:
            out.setdefault(co["id"], (co.get("en"), co.get("code")))
        for c in common.defense_companies():   # 방위 섹터 지도 — RHM.XETRA → RHM, 7012.TSE → 7012
            code = re.sub(r"\.[A-Z]+$", "", str(c.get("code") or "")) or None
            out.setdefault(c["id"], (c.get("name"), code))
        _LINES["tk"] = out
    return _LINES["tk"]


def stock_label(entity_ids):
    """'Marvell(MRVL)' — 보유 종목을 앞에, 최대 2개. 모르면 이름만, 아무것도 없으면 '시장'"""
    held = {h.get("id") for h in (common.load_yaml("config/portfolio.yaml") or {}).get("holdings") or []}
    labs = []
    for e in sorted(entity_ids or [], key=lambda e: e not in held):
        name, code = _tickers().get(e, (None, None))
        if name:
            name = re.sub(r",?\s+(Inc\.?|Corp\.?|Corporation|Ltd\.?|plc|Co\.,? Ltd\.?|Holdings|N.V.)$", "", name.strip())
            labs.append(f"{name}({code})" if code else name)
        if len(labs) == 2:
            break
    return "·".join(labs) or "시장"


def alert_time(item):
    """기사 공개 시각(KST). 오늘이 아니면 날짜를 붙인다"""
    from datetime import datetime
    raw = str(item.get("published_at") or item.get("detected_at") or "")
    try:
        t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        t = t.astimezone(common.now_kst().tzinfo) if t.tzinfo else t
    except ValueError:
        return raw[11:16]
    return t.strftime("%H:%M") if t.date() == common.now_kst().date() else t.strftime("%m/%d %H:%M")


PROFILES = common.ROOT / "config" / "company_profiles.yaml"
PROFILE_MAX_AGE_DAYS = 30   # 내러티브는 변한다 — 30일 지난 설명은 판정 모델이 새로 쓴 것으로 바꾼다
_SENT_RE = re.compile(r"(?<=[.!?。])\s+|(?<=다\.)\s*|\n+")


def _profiles():
    if "prof" not in _LINES:
        _LINES["prof"] = (common.load_yaml("config/company_profiles.yaml") or {}).get("profiles") or {}
    return _LINES["prof"]


def _fresh(as_of, days=PROFILE_MAX_AGE_DAYS):
    from datetime import date
    try:
        return (common.now_kst().date() - date.fromisoformat(str(as_of)[:10])).days <= days
    except ValueError:
        return False


def _narrative_summary(eid):
    """knowledge/narratives/companies/<id>.md 머리의 summary(30일 이내만) — narrative-premium 스킬이 쓴 지금의 내러티브"""
    f = common.ROOT / "knowledge" / "narratives" / "companies" / f"{eid}.md"
    if not f.exists():
        return None
    head = f.read_text(encoding="utf-8")[:1500]
    s, a = re.search(r"^summary:\s*(.+)$", head, re.M), re.search(r"^as_of:\s*(\S+)", head, re.M)
    return s.group(1).strip() if s and a and _fresh(a.group(1)) else None


def company_profile(entity_ids, model_lines=None, biz=None):
    """알림의 '☞ 회사 설명' 최대 3줄(마스터 지시 2026-10-29 "비즈니스 모델, 성장동력, 내러티브 등 3줄 정도").
    config/company_profiles.yaml(30일 이내) → 판정 모델이 준 3줄 → 기업 1줄 + 지금의 내러티브 요약. 지어내지 않는다(없으면 빈 목록)"""
    eids = list(entity_ids or [])
    for e in eids:
        p = _profiles().get(e)
        if p and p.get("lines") and _fresh(p.get("as_of")):
            return [l for l in p["lines"] if l][:3]
    lines = [l.strip() for l in (model_lines or []) if l and l.strip()][:3]
    if lines:
        return lines
    out = [x for x in (company_line(eids, biz), next((s for s in map(_narrative_summary, eids) if s), None)) if x]
    return out[:3]


def remember_profile(entity_ids, lines, source="판정 모델"):
    """판정 모델이 쓴 회사 설명 3줄을 저장(없거나 30일 지난 것만 바꿈) — 다음 알림부터 같은 설명을 다시 묻지 않는다"""
    lines = [l.strip() for l in (lines or []) if l and l.strip()][:3]
    eid = next(iter(entity_ids or []), None)
    if len(lines) < 2 or not eid:
        return False
    cur = _profiles().get(eid)
    if cur and _fresh(cur.get("as_of")):
        return False
    import yaml
    head = "".join(l + "\n" for l in PROFILES.read_text(encoding="utf-8").splitlines() if l.startswith("#")) if PROFILES.exists() else ""
    data = (common.load_yaml("config/company_profiles.yaml") or {}).get("profiles") or {}
    data[eid] = {"lines": lines, "as_of": common.now_kst().strftime("%Y-%m-%d"), "source": source}
    PROFILES.write_text(head + yaml.safe_dump({"profiles": data}, allow_unicode=True, sort_keys=False, width=200), encoding="utf-8")
    _LINES["prof"] = data
    return True


def snippet_points(item, n=3):
    """모델 요약이 없을 때의 핵심 줄 — 기사 요약문(snippet)에서 제목과 다른 문장만 최대 n개. 없으면 빈 목록(채우지 않는다)"""
    title = re.sub(r"\W+", "", (item.get("title") or "").lower())
    out = []
    for s in _SENT_RE.split(common.strip_tags(item.get("snippet") or "")):
        s = s.strip(" -·•")
        key = re.sub(r"\W+", "", s.lower())
        if len(key) < 12 or key in title or title[:40] in key:
            continue
        out.append(s if len(s) <= 90 else s[:88] + "…")
        if len(out) == n:
            break
    return out


def format_item(level, item, what=None, impact=None, card_id=None, biz=None, points=None, profile=None):
    """실시간 알림 — 마스터 지시 2026-10-29 양식:
        종목(종목코드)｜기사(원문 링크)｜시간
        ☞ 회사 설명 3줄(비즈니스 모델·성장 동력·내러티브)
        • 핵심 내용 1~3
    등급 코드는 드러내지 않는다(html_mode=True로 보낼 것). points·profile은 판정 모델 출력, 없으면 저장된 설명·요약문으로 채운다.
    level·what·impact·card_id는 호출 호환용(표기 안 함)"""
    title = html.escape(item.get("title") or "")
    url = item.get("url") or ""
    art = f'<a href="{html.escape(url, quote=True)}">{title}</a>' if url else title
    parts = [f"{html.escape(stock_label(item.get('entities_matched')))}｜{art}｜{alert_time(item)}"]
    prof = company_profile(item.get("entities_matched"), profile, biz)
    if prof:
        parts.append("☞ " + "\n".join(html.escape(l, quote=False) for l in prof))
    pts = [p.strip() for p in (points or []) if p and p.strip()][:3] or snippet_points(item)
    if pts:
        parts.append("\n".join(f"• {html.escape(p, quote=False)}" for p in pts))
    return "\n\n".join(parts)


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
    body = f"[Chiip Alerts · {len(rows)}]\n\n" + "\n\n─────────\n\n".join(r["text"] for r in rows)   # 건마다 3문단(2026-10-29 양식) — 구분선
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
        print(send(" ".join(sys.argv[1:]) or "Chiip 알림 시험", "TEST"))
