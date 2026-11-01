"""뉴스 원보도 추적 (마스터 지시 2026-11-02 "Pulse가 뉴스를 가져올 때 원문을 가져오는 구조가 잘 작동하는지 점검하라. FT의 최초 보도 기사를 인용한
Bloomberg 기사를 가져와서 전달하지 않는지")

재인용 기사('…, FT Says', '…, The Information reports - Reuters', '…: Report - CNBC')를 알아보고 원보도로 바꾼다.
찾는 순서: ① 수집함의 같은 사건 원보도 ② 수집하지 않는 매체(FT·Nikkei 등)는 Google News 색인에서 제목과 링크만. 해당 매체 사이트는 열지 않는다.
못 찾으면 재인용 기사를 그대로 두고 '원보도 ○○'를 표시한다. 재인용은 독립 확인이 아니다(CLAUDE.md origin_id).
사용: from origin import apply; item = apply(item)
"""
import json
import re
import urllib.parse
from datetime import datetime, timedelta

from pollers import common, rss

GENERIC = "미확인"
# 매체 이름 → (제목에 나오는 표기, Google News 도메인 제한, 수집 대상 여부)
OUTLETS = {
    "Financial Times": (r"FT|Financial Times", "ft.com", False),
    "Bloomberg": (r"Bloomberg(?:\.com)?(?: News)?", "bloomberg.com", True),
    "Reuters": (r"Reuters", "reuters.com", True),
    "WSJ": (r"WSJ|Wall Street Journal", "wsj.com", True),
    "The Information": (r"The Information", "theinformation.com", True),
    "Business Insider": (r"Business Insider", "businessinsider.com", True),
    "CNBC": (r"CNBC", "cnbc.com", True),
    "Nikkei": (r"Nikkei(?: Asia)?", "nikkei.com", False),
    "Semafor": (r"Semafor", "semafor.com", False),
    "Axios": (r"Axios", "axios.com", False),
    "Barron's": (r"Barron['’]?s", "barrons.com", False),
    "New York Times": (r"NYT|New York Times", "nytimes.com", False),
    "Washington Post": (r"Washington Post", "washingtonpost.com", False),
    "The Telegraph": (r"The Telegraph|Telegraph", "telegraph.co.uk", False),
    "Handelsblatt": (r"Handelsblatt", "handelsblatt.com", False),
    "DigiTimes": (r"DigiTimes", "digitimes.com", False),
    "Yonhap": (r"Yonhap", "yna.co.kr", False),
}
NAMES = "|".join(p for p, _, _ in OUTLETS.values())
SAYS = r"(?:says?|said|reports?|reported)"
END_RE = re.compile(rf"[,:;–—-]\s*(?:the\s+)?({NAMES})\s+{SAYS}\s*$", re.I)
START_RE = re.compile(rf"^(?:the\s+)?({NAMES})\s+(?:reports?|reported)\b", re.I)
ACCORDING_RE = re.compile(rf"\b(?:according to|citing|cited by|per)\s+(?:the\s+)?({NAMES})\b", re.I)
GENERIC_RE = re.compile(r"[,:;–—-]\s*(?:media\s+)?reports?(?:\s+says?|\s+said)?\s*$", re.I)
REPORTEDLY_RE = re.compile(r"\breportedly\b", re.I)
SCOOP_DESKS = ("Bloomberg", "Reuters", "WSJ", "The Information", "Financial Times")   # 이 매체의 'reportedly'는 자기 취재다
STOP = {"the", "a", "an", "of", "to", "in", "on", "for", "and", "as", "at", "by", "with", "its", "is", "are", "after", "from", "says", "said", "say",
        "reports", "report", "reported", "reportedly", "ft", "amid", "over", "into", "that", "this", "will", "be", "has", "have", "was", "were"}
POOL_HOURS = 72
SEARCH_DAYS = 3
_pool = {}


def outlet_of(name):
    """매체 이름을 표준 이름으로"""
    name = (name or "").strip()
    for std, (pat, _, _) in OUTLETS.items():
        if re.fullmatch(pat, name, re.I):
            return std
    return None


def body(item):
    """' - 매체' 꼬리를 뗀 제목"""
    title, pub = (item.get("title") or "").strip(), (item.get("publisher") or "").strip()
    head, sep, tail = title.rpartition(" - ")
    return head.strip() if sep and (tail.strip().lower() == pub.lower() or outlet_of(tail)) else title


def carrier(item):
    pub = (item.get("publisher") or "").strip()
    if not pub and " - " in (item.get("title") or ""):
        pub = item["title"].rsplit(" - ", 1)[1].strip()
    return outlet_of(pub) or pub


def cited(item):
    """이 기사가 인용한 매체 이름, 인용처를 밝히지 않은 재인용이면 GENERIC, 재인용이 아니면 None"""
    text, own = body(item), carrier(item)
    for rx in (END_RE, START_RE, ACCORDING_RE):
        m = rx.search(text)
        if m:
            who = outlet_of(m.group(1))
            return None if who == own else who
    if GENERIC_RE.search(text) or (REPORTEDLY_RE.search(text) and own not in SCOOP_DESKS):
        return GENERIC
    return None


def words(text):
    text = re.sub(rf"[,:;–—-]\s*(?:the\s+)?(?:{NAMES})\s+{SAYS}\s*$|[,:;–—-]\s*reports?(?:\s+says?)?\s*$", " ", text, flags=re.I)
    return {w for w in re.sub(r"[^a-z0-9$ ]", " ", text.lower()).split() if w not in STOP and len(w) > 1}


def overlap(a, b):
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def when(item):
    try:
        return datetime.fromisoformat(str(item.get("saved_at") or item.get("detected_at") or item.get("published_at")))
    except ValueError:
        return None


def pool(now):
    """지난 POOL_HOURS 수집 기사 — 회차마다 한 번만 읽는다"""
    key = now.strftime("%Y%m%d%H")
    if key in _pool:
        return _pool[key]
    rows = []
    for k in range(POOL_HOURS // 24 + 1):
        day = common.INBOX / (now - timedelta(days=k)).strftime("%Y%m%d")
        for f in day.glob("*.json") if day.exists() else []:
            try:
                it = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if it.get("title") and it.get("url") and carrier(it):
                rows.append(it)
    _pool.clear()
    _pool[key] = rows
    return rows


def find_original(item, who, rows, now):
    """수집함에서 같은 사건의 원보도. who가 GENERIC이면 취재 매체의 더 이른 기사 중 같은 종목·같은 사건인 것"""
    w, ents = words(body(item)), set(item.get("entities_matched") or [])
    start, best = when(item), None
    for c in rows:
        if c.get("item_id") == item.get("item_id") or cited(c):
            continue
        own = carrier(c)
        shared_ent = bool(ents & set(c.get("entities_matched") or []))
        if who == GENERIC and (own not in SCOOP_DESKS or not shared_ent):
            continue
        if who != GENERIC and own != who:
            continue
        cw, seen = words(body(c)), when(c)
        need = 0.25 if shared_ent and who != GENERIC else 0.4
        if overlap(w, cw) < need or len(w & cw) < 2 or not seen or (start and seen.tzinfo and start.tzinfo and seen > start + timedelta(hours=1)):
            continue
        if not best or seen < best[0]:
            best = (seen, c)
    return best[1] if best else None


def lookup(item, who):
    """수집하지 않는 매체의 원보도 제목·링크 — Google News 색인만 본다"""
    site = OUTLETS[who][1]
    w = words(body(item))
    names = [x for x in re.sub(r"[^A-Za-z0-9$ ]", " ", body(item)).split() if x.lower() in w]
    heads = [x for x in names if x[0].isupper()][:2]   # 고유명사는 모두 맞아야 한다 — 'AI' 하나로 다른 기사를 잡지 않는다
    rest = [x for x in names if x not in heads][:6]
    q = f"site:{site} {' '.join(heads)} ({' OR '.join(rest)}) when:{SEARCH_DAYS}d"
    try:
        entries = rss.parse_feed(common.http_get(rss.GNEWS.format(q=urllib.parse.quote(q), hl="en-US", gl="US")))
    except Exception as exc:   # 찾기가 실패해도 알림은 나간다
        print(f"원보도 찾기 실패 {who}: {type(exc).__name__}")
        return None
    rows = [(overlap(w, words(body({"title": e.get("title"), "publisher": e.get("publisher")}))), e) for e in entries if outlet_of(e.get("publisher")) == who]
    share, e = max(rows, key=lambda r: r[0], default=(0, None))
    if not e or share < 0.3 or len(w & words(body({"title": e.get("title"), "publisher": e.get("publisher")}))) < 3:
        return None
    return {"title": e["title"], "url": e["link"], "publisher": who}


def apply(item, now=None, search=True):
    """재인용 기사면 원보도로 바꾼 복사본을 돌려준다. relay에 경로를 남긴다. 재인용이 아니면 그대로"""
    who = cited(item)
    if not who:
        return item
    now = now or common.now_kst()
    out = dict(item)
    rel = {"outlet": None if who == GENERIC else who, "carrier": carrier(item), "relay_url": item.get("url"), "found": False}
    orig = find_original(item, who, pool(now), now)
    if not orig and search and who != GENERIC and not OUTLETS[who][2]:
        orig = lookup(item, who)
    if orig:
        out.update(title=orig["title"], url=orig["url"], publisher=orig.get("publisher") or who)
        rel.update(outlet=rel["outlet"] or carrier(orig), found=True, inferred=who == GENERIC)
    out["relay"] = rel
    return out


def line(rel):
    """알림에 붙는 출처 줄(HTML)"""
    who = rel.get("outlet")
    relay = f'<a href="{rel["relay_url"]}">{rel["carrier"]}</a>' if rel.get("relay_url") else rel.get("carrier")
    if rel.get("found"):
        return f"{'먼저 나온 보도' if rel.get('inferred') else '원보도'} {who} · 재인용 {relay}"
    return f"원보도 {who}(원문 못 찾음) · 재인용 {relay}" if who else f"재인용 보도, 원보도 미확인 · 전달 {relay}"
