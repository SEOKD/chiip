"""숏 리포트 대상 회사 사이트 직접 감시 — 사이트맵 lastmod로 새·고친 블로그·뉴스·IR 글을 잡는다 (2026-11-09 시의성 점검:
Cerebras가 Culper 수명 주장을 반박한 회사 블로그(2026-11-05 14:00 UTC)를 8-K·보도자료·언론 색인만 보다가 3일 뒤 2차 보도(MLQ.ai 11/8)로 잡았다)

config/short_watch.yaml target_sites — 회사마다 사이트맵(색인이면 하위까지 한 단계)과 경로 정규식(블로그·뉴스·IR).
lastmod가 지난 lookback_h 안이고 처음 보는 (url, lastmod)면 inbox 항목(src-company-sites, 보도 무관 원문)으로 낸다. 첫 회차는 기준선만.
robots.txt를 지키고, 막히면 건너뛴다. 대상은 숏 캠페인이 열린 회사 — Pulse가 새 숏 리포트를 판정하면 이 목록에 회사를 더한다(docs/tasks/chiip-pulse.md).
"""
import hashlib
import re
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from . import common

SRC = "src-company-sites"
NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def _robots_ok(url):
    p = urllib.parse.urlparse(url)
    rp = urllib.robotparser.RobotFileParser()
    try:
        rp.parse(common.http_get(f"{p.scheme}://{p.netloc}/robots.txt", timeout=15).decode("utf-8", "ignore").splitlines())
    except Exception:
        return True   # robots.txt가 없으면 허용으로 본다(표준)
    return rp.can_fetch(common.UA if hasattr(common, "UA") else "*", url)


def _ts(s):
    try:
        t = datetime.fromisoformat(s.strip().replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def entries(sitemap, depth=1):
    """[(url, lastmod datetime|None)] — 사이트맵 색인이면 하위 사이트맵을 한 단계 더 읽는다"""
    root = ET.fromstring(common.http_get(sitemap, timeout=25))
    if root.tag.endswith("sitemapindex"):
        out = []
        for sm in root.iter(NS + "sitemap"):
            loc = sm.findtext(NS + "loc")
            if loc and depth > 0:
                try:
                    out += entries(loc.strip(), depth - 1)
                except Exception:
                    continue
        return out
    return [(u.findtext(NS + "loc").strip(), _ts(u.findtext(NS + "lastmod") or "")) for u in root.iter(NS + "url") if u.findtext(NS + "loc")]


def poll(env=None, now=None):
    cfg = common.load_yaml("config/short_watch.yaml") or {}
    sites = cfg.get("target_sites") or []
    look = timedelta(hours=float(cfg.get("target_lookback_h") or 72))
    st = common.load_state("company_sites", {"seen": {}})
    now = now or datetime.now(timezone.utc)
    items, errors = [], []
    for s in sites:
        try:
            if not _robots_ok(s["sitemap"]):
                errors.append(f"{s['company']}: robots 차단")
                continue
            rx = re.compile(s.get("path") or r"/(blog|news|press|newsroom|investors?)/", re.I)
            prev = st["seen"].get(s["sitemap"])   # 사이트맵 단위(한 회사에 사이트맵이 여럿일 수 있다)
            keys = {}
            for url, lm in entries(s["sitemap"]):
                if not rx.search(url):
                    continue
                k = f"{url}|{lm.isoformat() if lm else ''}"
                keys[k] = 1
                if prev is not None and k not in prev and (lm is None or now - lm <= look):
                    title = urllib.parse.unquote(url.rstrip("/").rsplit("/", 1)[-1]).replace("-", " ")
                    items.append(common.make_item(SRC, hashlib.sha1(k.encode()).hexdigest()[:16], url, f"[{s['company']} company site] {title}",
                                                  common.iso(lm.astimezone(timezone(timedelta(hours=9)))) if lm else common.iso(common.now_kst()),
                                                  "회사 원문", "en", f"sitemap lastmod {lm.isoformat() if lm else 'none'} — short-campaign target company post",
                                                  extra={"entity_ids": s.get("entity_ids") or [], "source_class": "회사 원문", "short_target": s.get("campaign")}))
            st["seen"][s["sitemap"]] = sorted(set(prev or []) | set(keys))[-5000:]
        except Exception as exc:
            errors.append(f"{s['company']}: {type(exc).__name__}")
    common.save_state("company_sites", st)
    if errors and len(errors) == len(sites):
        raise RuntimeError("대상 회사 사이트 전부 실패: " + ", ".join(errors[:5]))
    if errors:
        print("대상 회사 사이트 일부 건너뜀:", ", ".join(errors))
    return items
