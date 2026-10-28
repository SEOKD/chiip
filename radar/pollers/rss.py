"""RSS/Atom 폴러 — 기업 뉴스룸(B), Google News 쿼리(F), 뉴스레터(L8) 공통

source_registry.yaml 에서 method: rss 이고 feed_url(또는 feed_queries)이 있는 원천을 읽는다.
"""
import hashlib
import re
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
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


def _older_than(iso_s, days):
    """날짜를 못 읽으면(정적 페이지 등) 오래된 것으로 본다"""
    try:
        dt = datetime.fromisoformat(iso_s.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=common.KST)
    return common.now_kst() - dt > timedelta(days=days)


# 마스터 지정 매체(7곳 → 9곳, 2026-10-28 CNBC·Seeking Alpha 추가). 두 곳은 robots.txt가 AI 수집기를 막아 Google News 색인으로만 본다
NEWS7_SITES = ("(site:reuters.com OR site:bloomberg.com OR site:wsj.com OR site:theinformation.com OR site:businessinsider.com"
               " OR site:cnbc.com OR site:seekingalpha.com)")


def focus7_urls(src, chunk=8):
    from . import gate
    focus, _ = gate.focus_state()
    uni = list((common.load_yaml("config/valuation.yaml") or {}).get("universe", []))
    uni += (common.load_yaml("config/earnings_watch.yaml") or {}).get("extra") or []   # 알파·마스터 Stocks·레이더 테마 종목도
    names, seen = [], set()
    for u in uni:
        if u["id"] in seen:
            continue
        seen.add(u["id"])
        if focus is not None and u["id"] not in focus:
            continue
        if u.get("region") == "KR":  # 영문 매체 검색엔 영문명이 필요 — 한국 종목은 universe의 en 또는 lexicon 영문명
            lex = common.load_yaml(f"config/lexicon/{u['id']}.yaml") or {}
            en = u.get("en") or ((lex.get("names") or {}).get("en") or [None])[0]
            if not en:
                continue
            names.append(en)
        else:
            names.append((u.get("aliases") or [u["name"]])[0].strip())
    for i in range(0, len(names), chunk):
        q = f"{NEWS7_SITES} (" + " OR ".join(f'"{n}"' for n in names[i:i + chunk]) + ") when:1d"
        yield GNEWS.format(q=urllib.parse.quote(q), hl="en-US", gl="US"), None


def feed_urls(src):
    if src.get("feed_url"):
        yield src["feed_url"], None
    for u in src.get("feed_urls", []) or []:
        yield u, None
    for q in src.get("feed_queries", []) or []:
        if q == "@focus7":  # 포커스 종목 × 마스터 지정 7개 매체(도메인 제한), 8종목씩 묶어 한 쿼리
            yield from focus7_urls(src)
            continue
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
    # 잡음이 많은 원천(정부 피드·도메인 제한 검색)은 include_regex에 맞는 글만 받는다
    inc = re.compile(src["include_regex"], re.I) if src.get("include_regex") else None
    max_age = src.get("max_age_days")
    urls = list(feed_urls(src))
    failed = []
    for url, entity in urls:
        try:
            entries = parse_feed(common.http_get(url))
        except Exception as exc:  # 피드 여럿 중 하나가 죽어도 나머지는 받는다
            if len(urls) == 1:
                raise
            failed.append(f"{url[:60]}: {type(exc).__name__}")
            continue
        for e in entries:
            if not e["link"]:
                continue
            if inc and not inc.search(f"{e['title']} {common.strip_tags(e['desc'])}"):
                continue
            if max_age and _older_than(to_iso(e["date"]), max_age):  # site: 쿼리는 when:이 잘 안 먹어 옛 문서가 섞인다
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
    if failed and len(failed) == len(urls):
        raise RuntimeError("피드 전부 실패: " + "; ".join(failed[:3]))
    # 뉴스룸처럼 scope가 단일 기업이면 매칭 보강
    scope = src.get("scope") or []
    if len(scope) == 1 and str(scope[0]).startswith("co-"):
        for it in items:
            if scope[0] not in it["entities_matched"]:
                it["entities_matched"].append(scope[0])
    return items
