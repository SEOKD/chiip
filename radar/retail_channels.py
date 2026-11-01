"""리테일 채널 집계 — 레딧·X에 직접 접속하지 않고 개인투자자 반응을 모은다(마스터 지시 2026-11-01 "MCP가 불가능하거나 유료 API 키가 필요한 레딧, X에 직접 접속하지 말고").

키 없이 쓰고 robots.txt를 확인한 원천만 쓴다(2026-11-01 접속 점검). 수만 저장하고 글 본문·작성자는 저장하지 않는다.
  종목별: reddit_mentions(ApeWisdom 집계) · wsb_comments(Tradestie 집계) · wiki_views(Wikimedia 7일 조회) · hn(Hacker News 7일 글 수) · lemmy(7일 글 수) · margin_tw(TWSE 공식 신용잔고)
  시장별: trends(Google Trends 급상승 RSS) · kalshi(개인 베팅 시장 확률) → knowledge/models/discovery/retail_latest.json
radar/attention.py가 하루 1회 부른다. 설정 config/discovery.yaml attention.sources.retail.
"""
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

UA = {"User-Agent": "Chiip research fhteo1101@gmail.com"}
APE = "https://apewisdom.io/api/v1.0/filter/all-stocks/page/{p}"
TRADESTIE = "https://tradestie.com/api/v1/apps/reddit"
WIKI = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{title}/daily/{start}/{end}"
HN = "https://hn.algolia.com/api/v1/search?query={q}&tags=story&hitsPerPage=1&numericFilters=created_at_i%3E{ts}"
LEMMY = "https://lemmy.world/api/v3/search?q={q}&type_=Posts&sort=New&limit=50"
TWSE = "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN"
TRENDS = "https://trends.google.com/trending/rss?geo={geo}"
KALSHI = "https://api.elections.kalshi.com/trade-api/v2/events?status=open&limit=200&with_nested_markets=true"
SUFFIX = re.compile(r"[,\s]+(International|Incorporated|Inc\.?|Corporation|Corp\.?|Co\.,?\s*Ltd\.?|Ltd\.?|Holdings?|Group|Gruppen|Industries|plc|PLC|AG|SE|N\.V\.|ASA)\b.*$")
OUT = common.ROOT / "knowledge" / "models" / "discovery" / "retail_latest.json"


def _json(url, fetch=None):
    return json.loads((fetch or (lambda u: common.http_get(u, headers=UA, timeout=25)))(url))


def ape_all(fetch=None, max_pages=12):
    """{티커: 언급 수} — ApeWisdom 상위 목록"""
    out, page, pages = {}, 1, 1
    while page <= min(pages, max_pages):
        d = _json(APE.format(p=page), fetch)
        pages = int(d.get("pages") or 1)
        out.update({r["ticker"]: r.get("mentions") for r in d.get("results") or [] if r.get("ticker")})
        page += 1
    return out


def tradestie_all(fetch=None):
    """({티커: 댓글 수}, {티커: 강세/약세}) — WSB 상위 50"""
    rows = _json(TRADESTIE, fetch)
    return {r["ticker"]: r.get("no_of_comments") for r in rows if r.get("ticker")}, {r["ticker"]: r.get("sentiment") for r in rows if r.get("ticker")}


def short_name(name):
    """검색용 이름 — 'CACI International' → 'CACI'"""
    return SUFFIX.sub("", str(name)).strip() or str(name)


def wiki_views(title, days=7, fetch=None, today=None):
    """최근 7일 조회 수 — 전체 이름과 줄인 이름 중 큰 값(Wikimedia는 넘겨주기 문서를 따라가지 않는다). 문서가 없으면 None"""
    end = today or datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    best = None
    for name in dict.fromkeys((str(title), short_name(title))):
        url = WIKI.format(title=urllib.parse.quote(name.replace(" ", "_"), safe=""), start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"))
        try:
            n = sum(int(x.get("views") or 0) for x in _json(url, fetch).get("items") or [])
            best = n if best is None else max(best, n)
        except Exception:
            continue
    return best


def hn_count(name, days=7, fetch=None, now=None):
    ts = int((now or time.time()) - days * 86400)
    try:
        return int(_json(HN.format(q=urllib.parse.quote(f'"{name}"'), ts=ts), fetch).get("nbHits") or 0)
    except Exception:
        return None


def lemmy_count(name, days=7, fetch=None, now=None):
    cut = datetime.fromtimestamp((now or time.time()) - days * 86400, timezone.utc).isoformat()[:19]
    try:
        posts = _json(LEMMY.format(q=urllib.parse.quote(f'"{name}"')), fetch).get("posts") or []
        return sum(1 for p in posts if str((p.get("post") or {}).get("published"))[:19] >= cut)
    except Exception:
        return None


ARCTIC = "https://arctic-shift.photon-reddit.com/api/posts/search"


def arctic_titles(subs, days=7, fetch=None, now=None, limit=100):
    """레딧 보관소 Arctic Shift에서 게시판별 최근 글 제목을 한 번씩 받는다 — 회사별 검색은 시간 초과가 나서 내려받아 여기서 센다. 제목은 세는 데만 쓰고 저장하지 않는다(2026-11-01 마스터 지시, 레딧 직접 접속 없음)"""
    after = ((now or datetime.now(timezone.utc)) - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    for sub in subs:
        d = _json(f"{ARCTIC}?{urllib.parse.urlencode({'subreddit': sub, 'after': after, 'limit': limit, 'sort': 'desc', 'fields': 'title'})}", fetch)
        out += [str(x.get("title") or "") for x in d.get("data") or []]
        time.sleep(1)
    return out


def title_hits(titles, name, tick=None):
    pats = [re.compile(rf"(?<![A-Za-z]){re.escape(x)}(?![A-Za-z])", re.I) for x in (name, tick) if x and len(x) >= 3]
    return sum(1 for t in titles if any(p.search(t) for p in pats))


def twse_margin(fetch=None):
    """{종목코드: 신용 매수 잔고(천 주)} — TWSE 공식, 개인 빚투의 대리 지표"""
    out = {}
    for r in _json(TWSE, fetch):
        v = str(r.get("融資今日餘額") or "").replace(",", "")
        if v.isdigit():
            out[str(r.get("股票代號"))] = int(v)
    return out


def trends(geos, fetch=None):
    """{나라: [급상승 검색어…]}"""
    get = fetch or (lambda u: common.http_get(u, headers=UA, timeout=25))
    out = {}
    for g in geos:
        try:
            out[g] = [x.findtext("title") for x in ET.fromstring(get(TRENDS.format(geo=g))).iter("item")]
        except Exception:
            out[g] = []
    return out


def kalshi(keywords, top=15, fetch=None):
    """경제·금융·기업 분야에서 키워드에 맞는 공개 사건 — 제목과 가장 유력한 선택지·가격만(스포츠 묶음 시장은 뺀다)"""
    pat = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in keywords) + r")\b", re.I)
    out = []
    for e in _json(KALSHI, fetch).get("events") or []:
        if e.get("category") not in ("Economics", "Financials", "Companies", "Politics") or not pat.search(str(e.get("title"))):
            continue
        ms = e.get("markets") or []
        price = lambda m: float(m.get("yes_ask_dollars") or m.get("last_price_dollars") or 0)
        lead = max(ms, key=price) if ms else {}
        out.append({"title": e.get("title"), "lead": lead.get("yes_sub_title") or lead.get("title"), "yes": price(lead) if lead else None, "category": e.get("category")})
    return out[:top]


def us_ticker(c):
    """미국 상장 티커 — 없으면 None"""
    code = str(c.get("code") or c.get("ticker") or "")
    if code.endswith(".US"):
        return code[:-3]
    return code if code and c.get("market", "us") == "us" and not code[:1].isdigit() else None


def tw_code(c):
    m = re.match(r"(\d{4,6})(?:\.(?:TW|TWO))?$", str(c.get("code") or ""))
    return m.group(1) if m and c.get("market") == "tw" else None


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k), None
    except Exception as exc:
        return None, f"{fn.__name__} {type(exc).__name__}"


def collect(cands, today, cfg=None, fetch=None, pause=0.15):
    """(rows, notes, 시장 스냅숏) — rows는 attention.csv와 같은 (날짜, id, 원천, 수). 원천 하나가 실패해도 나머지는 간다"""
    cfg = cfg or {}
    notes = []
    ape, e1 = _safe(ape_all, fetch)
    wsb, e2 = _safe(tradestie_all, fetch)
    margin, e3 = _safe(twse_margin, fetch)
    titles, e6 = _safe(arctic_titles, cfg.get("arctic_subs") or ["wallstreetbets", "stocks", "investing", "semiconductors", "SkincareAddiction", "gaming"], 7, fetch)
    notes += [e for e in (e1, e2, e3, e6) if e]
    wsb_n, wsb_sent = wsb or ({}, {})
    rows = []
    for cid, c in cands.items():
        name, tick, tw = c.get("name"), us_ticker(c), tw_code(c)
        if tick and ape is not None:
            rows.append((today, cid, "reddit_mentions", ape.get(tick, 0)))
        if tick and wsb is not None:
            rows.append((today, cid, "wsb_comments", wsb_n.get(tick, 0)))
        if tw and margin is not None and tw in margin:
            rows.append((today, cid, "margin_tw", margin[tw]))
        if name:
            rows.append((today, cid, "wiki_views", wiki_views(c.get("wiki") or name, fetch=fetch)))
            rows.append((today, cid, "hn", hn_count(short_name(name), fetch=fetch)))
            rows.append((today, cid, "lemmy", lemmy_count(short_name(name), fetch=fetch)))
            if titles:
                rows.append((today, cid, "reddit_titles", title_hits(titles, short_name(name), tick)))
        if pause:
            time.sleep(pause)
    hot, e4 = _safe(trends, cfg.get("trend_geos") or ["US", "KR", "JP", "TW"], fetch)
    bets, e5 = _safe(kalshi, cfg.get("kalshi_keywords") or ["Fed", "tariff", "recession", "defense", "Nvidia"], 15, fetch)
    notes += [e for e in (e4, e5) if e]
    names = {cid: short_name(c.get("name")).lower() for cid, c in cands.items() if c.get("name")}
    hits = sorted({cid for v in (hot or {}).values() for t in v for cid, n in names.items() if t and n in str(t).lower()})
    for cid in hits:
        rows.append((today, cid, "trends_hit", 1))
    snap = {"date": today, "wsb_sentiment": wsb_sent, "trends": hot or {}, "kalshi": bets or [], "errors": notes}
    return [r for r in rows if r[3] is not None], notes, snap


def save(snap):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
