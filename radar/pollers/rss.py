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
# 포화 분할용 매체 묶음 — 한 종목만으로도 100건 상한에 닿으면(엔비디아 등) 주요 4곳과 나머지로 나눠 다시 묻는다
NEWS7_SITE_GROUPS = ("(site:reuters.com OR site:bloomberg.com OR site:wsj.com OR site:theinformation.com)",
                     "(site:businessinsider.com OR site:cnbc.com OR site:seekingalpha.com)")
GNEWS_CAP = 95   # Google News RSS는 한 쿼리 최대 100건 — 이 이상이면 최신 기사가 잘렸을 수 있다(2026-10-29 측정: 14개 쿼리 중 7개 포화)


FOCUS7_WINDOW = "6h"        # 15분마다 도는 회차는 최근 6시간만 묻는다(포화 줄이기) — when:은 시간 단위도 먹는다(2026-10-29 시험)
FOCUS7_SWEEP_H = 3           # 3시간마다 한 번은 when:1d로 빠진 것 쓸어 담기


def _focus7_url(names, sites=NEWS7_SITES, window="1d"):
    q = f"{sites} (" + " OR ".join(f'"{n}"' for n in names) + f") when:{window}"
    return GNEWS.format(q=urllib.parse.quote(q), hl="en-US", gl="US")


def focus7_entries(names, sites=NEWS7_SITES, stats=None, window="1d"):
    """포화(100건 상한)면 종목을 반으로 나눠 다시 묻고, 한 종목이면 매체 묶음으로 나눈다 — 상한에 밀려 최신 기사가 빠지던 문제
    (MRVL–Lumentum 보도 지연·누락 점검, 2026-10-29). stats는 {"requests": n, "saturated": n}"""
    import time
    entries = parse_feed(common.http_get(_focus7_url(names, sites, window)))
    if stats is not None:
        stats["requests"] = stats.get("requests", 0) + 1
    if len(entries) < GNEWS_CAP:
        return entries
    if stats is not None:
        stats["saturated"] = stats.get("saturated", 0) + 1
    time.sleep(0.3)
    if len(names) > 1:
        mid = len(names) // 2
        parts = [focus7_entries(names[:mid], sites, stats, window), focus7_entries(names[mid:], sites, stats, window)]
    elif sites == NEWS7_SITES:
        parts = [focus7_entries(names, g, stats, window) for g in NEWS7_SITE_GROUPS]
    else:
        return entries   # 한 종목·한 매체 묶음도 포화 — 더 나누지 않는다(상태에 포화로 남음)
    seen, out = set(), []
    for e in entries + [x for part in parts for x in part]:
        if e["link"] and e["link"] not in seen:
            seen.add(e["link"])
            out.append(e)
    return out


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
        yield "@focus7", names[i:i + chunk]   # poll_source가 focus7_entries로 포화 분할하며 받는다


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
    stats, window = {}, FOCUS7_WINDOW
    if any(u == "@focus7" for u, _ in urls):
        st7 = common.load_state("focus7_stats", {})
        last = (st7.get("sweep") or {}).get(src["id"])
        if not last or datetime.fromisoformat(last) < common.now_kst() - timedelta(hours=FOCUS7_SWEEP_H):
            window = "1d"
    for url, entity in urls:
        try:
            if url == "@focus7":
                entries, entity = focus7_entries(entity, stats=stats, window=window), None
            else:
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
            if e.get("publisher") or src.get("publisher"):   # 매체 직접 RSS는 원천에 매체명을 적는다(2026-10-29 Bloomberg 직접 피드)
                extra["publisher"] = (e.get("publisher") or src["publisher"]).strip()
            if entity:
                extra["query_entity"] = entity
            it = common.make_item(
                src["id"], hashlib.sha1(e["link"].encode()).hexdigest()[:16], e["link"],
                common.strip_tags(e["title"]), to_iso(e["date"]), src.get("doc_type", "기사"),
                src.get("language", "ko"), common.strip_tags(e["desc"]), extra=extra)
            if entity and entity not in it["entities_matched"]:
                it["entities_matched"].append(entity)
            items.append(it)
    if stats:
        st = common.load_state("focus7_stats", {})
        st[src["id"]] = {**stats, "window": window, "queries": sum(1 for u, _ in urls if u == "@focus7"), "at": common.iso(common.now_kst())}
        if window == "1d":
            st.setdefault("sweep", {})[src["id"]] = common.iso(common.now_kst())
        common.save_state("focus7_stats", st)
    if failed and len(failed) == len(urls):
        raise RuntimeError("피드 전부 실패: " + "; ".join(failed[:3]))
    # 뉴스룸처럼 scope가 단일 기업이면 매칭 보강
    scope = src.get("scope") or []
    if len(scope) == 1 and str(scope[0]).startswith("co-"):
        for it in items:
            if scope[0] not in it["entities_matched"]:
                it["entities_matched"].append(scope[0])
    return items
