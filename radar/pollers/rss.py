"""RSS/Atom 폴러 — 기업 뉴스룸(B), Google News 쿼리(F), 뉴스레터(L8) 공통

source_registry.yaml 에서 method: rss 이고 feed_url(또는 feed_queries)이 있는 원천을 읽는다.
"""
import hashlib
import urllib.parse
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

from . import common

ATOM = "{http://www.w3.org/2005/Atom}"
GNEWS = "https://news.google.com/rss/search?q={q}&hl={hl}&gl={gl}&ceid={gl}:{hl}"


def parse_feed(raw):
    root = ET.fromstring(raw)
    out = []
    for it in root.iter("item"):
        out.append({"title": it.findtext("title") or "", "link": it.findtext("link") or "",
                    "date": it.findtext("pubDate") or "", "desc": it.findtext("description") or "",
                    "publisher": it.findtext("source") or ""})
    for it in root.iter(f"{ATOM}entry"):
        link = it.find(f"{ATOM}link")
        out.append({"title": it.findtext(f"{ATOM}title") or "", "link": link.get("href") if link is not None else "",
                    "date": it.findtext(f"{ATOM}updated") or it.findtext(f"{ATOM}published") or "",
                    "desc": it.findtext(f"{ATOM}summary") or ""})
    return out


def to_iso(s):
    if not s:
        return ""
    try:
        return common.iso(parsedate_to_datetime(s))
    except (TypeError, ValueError):
        return s  # Atom은 이미 ISO


def feed_urls(src):
    if src.get("feed_url"):
        yield src["feed_url"], None
    for q in src.get("feed_queries", []) or []:
        if q == "@watchlist":
            for row in common.load_watchlist():
                if row["tier"] in src.get("scope", ["T0"]):
                    name = row["name"].split("(")[0].strip()
                    yield GNEWS.format(q=urllib.parse.quote(f'"{name}" when:1d'),
                                       hl=src.get("hl", "ko"), gl=src.get("gl", "KR")), row["entity_id"]
        else:
            ents = common.match_entities(q)
            yield (GNEWS.format(q=urllib.parse.quote(q), hl=src.get("hl", "ko"), gl=src.get("gl", "KR")),
                   ents[0] if ents else None)


def poll_source(src):
    items = []
    for url, entity in feed_urls(src):
        for e in parse_feed(common.http_get(url)):
            if not e["link"]:
                continue
            extra = {"tier": src.get("tier_hint")}
            if e.get("publisher"):
                extra["publisher"] = e["publisher"].strip()
            if entity:
                extra["query_entity"] = entity
            it = common.make_item(
                src["id"], hashlib.sha1(e["link"].encode()).hexdigest()[:16], e["link"],
                common.strip_tags(e["title"]), to_iso(e["date"]), src.get("doc_type", "기사"),
                src.get("language", "ko"), common.strip_tags(e["desc"]), extra=extra)
            if entity and entity not in it["entities_matched"]:
                it["entities_matched"].append(entity)
            items.append(it)
    # 뉴스룸처럼 scope가 단일 기업이면 매칭 보강
    scope = src.get("scope") or []
    if len(scope) == 1 and str(scope[0]).startswith("co-"):
        for it in items:
            if scope[0] not in it["entities_matched"]:
                it["entities_matched"].append(scope[0])
    return items
