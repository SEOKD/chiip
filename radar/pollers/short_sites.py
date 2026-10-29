"""숏 운용사 원문 사이트 직접 감시 (2026-10-29 마스터 지시 — "CBRS 숏 리포트나 Marvell의 Lumentum 인수 기사 같은 걸 즉시 찾아오는
파이프라인" 점검에서, 숏 리포트는 Google News 색인·제3자 글로만 잡혀 원문보다 몇 시간 늦는 구멍이 확인됨).

config/short_watch.yaml sites — 운용사마다
  feed: 공개 RSS(WordPress·Substack /feed) → 새 글
  page: 피드가 없으면 리서치 목록 페이지의 같은 도메인 링크를 직전 회차와 비교 → 새 링크(첫 회차는 기준선만 저장)
robots.txt를 매 회차 확인해 막히면 건너뛴다. 403·로그인·유료벽은 우회하지 않는다(Culper·Iceberg·Ningi·Jehoshaphat는 403 → Google News 색인만).
저장은 제목·링크만. 판정 상향은 radar/promote.py(이 원천의 글은 대상 종목이 보이면 숏 리포트로 P1, 보유 종목이면 P0)."""
import hashlib
import html as htmllib
import re
import urllib.parse
import urllib.robotparser

from pollers import common
from pollers import rss

SRC = "src-short-sites"
UA = "chiip-radar/0.1 (personal research)"
LINK_RE = re.compile(r'<a\s[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.I | re.S)
NAV_RE = re.compile(r"^(home|about|contact|team|disclaimer|privacy|terms|subscribe|log ?in|sign ?up|research|reports?|blog|news|archive|"
                    r"read more|more|next|previous|older|newer|twitter|linkedin|email|menu|search|faq|careers|legal)\b", re.I)


def _robots_ok(base):
    rp = urllib.robotparser.RobotFileParser()
    try:
        raw = common.http_get(base.rstrip("/") + "/robots.txt", timeout=10)
        raw = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw
        rp.parse([] if "<html" in raw[:300].lower() else raw.splitlines())
    except Exception:
        rp.parse([])   # robots.txt가 없으면(404) 제한 없음 — 표준 해석
    return rp.can_fetch(UA, base) and rp.can_fetch("ClaudeBot", base)


def page_links(html_text, base):
    """같은 도메인, 글자 수 12자 이상, 메뉴 문구가 아닌 링크 → {url: 제목}"""
    host = urllib.parse.urlparse(base).netloc.replace("www.", "")
    out = {}
    for href, inner in LINK_RE.findall(html_text or ""):
        title = re.sub(r"\s+", " ", htmllib.unescape(common.strip_tags(inner))).strip()
        url = urllib.parse.urljoin(base, href.strip())
        u = urllib.parse.urlparse(url)
        if u.scheme not in ("http", "https") or u.netloc.replace("www.", "") != host:
            continue
        if len(title) < 12 or NAV_RE.match(title) or re.search(r"\.(css|js|png|jpg|svg|ico)$", u.path, re.I):
            continue
        if u.path.rstrip("/") in ("", "/") or url.rstrip("/") == base.rstrip("/"):
            continue
        out.setdefault(url, title)
    return out


def _item(site, url, title, published=None):
    return common.make_item(SRC, hashlib.sha1(url.encode()).hexdigest()[:16], url, title,
                            published or common.iso(common.now_kst()), "숏 리포트", "en", "",
                            extra={"publisher": site["firm"], "source_class": "숏 리포트"})


def poll(env=None):
    sites = (common.load_yaml("config/short_watch.yaml") or {}).get("sites") or []
    st = common.load_state("short_sites", {"pages": {}})
    items, errors = [], []
    for site in sites:
        base = site["url"]
        try:
            if not _robots_ok(base):
                errors.append(f"{site['firm']}: robots 차단")
                continue
            if site.get("feed"):
                for e in rss.parse_feed(common.http_get(site["feed"], timeout=20)):
                    if e["link"] and not rss._older_than(rss.to_iso(e["date"]), 3):
                        items.append(_item(site, e["link"], common.strip_tags(e["title"]), rss.to_iso(e["date"])))
            else:
                raw = common.http_get(site.get("page") or base, timeout=20)
                raw = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw
                links = page_links(raw, site.get("page") or base)
                prev = st["pages"].get(site["firm"])
                if prev is not None:   # 첫 회차는 기준선만
                    for url, title in links.items():
                        if url not in prev:
                            items.append(_item(site, url, title))
                st["pages"][site["firm"]] = sorted(set(prev or []) | set(links))[-500:]
        except Exception as exc:   # 사이트 하나가 죽어도 나머지는 본다
            errors.append(f"{site['firm']}: {type(exc).__name__}")
    common.save_state("short_sites", st)
    if errors and len(errors) == len(sites):
        raise RuntimeError("숏 운용사 사이트 전부 실패: " + ", ".join(errors[:5]))
    if errors:
        print("숏 운용사 사이트 일부 건너뜀:", ", ".join(errors))
    return items
