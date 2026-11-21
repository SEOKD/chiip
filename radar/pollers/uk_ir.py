"""영국 상장사 규제 공시(RNS)·보도자료 — 회사 IR 페이지의 공개 피드 직접 감시 (원천 src-uk-ir, 설정 config/uk_ir.yaml)
(마스터 지시 2026-11-22 "1번 기준으로 파이프라인을 만들어라" — Investegate·LSE는 약관이 자동 접근·상업 이용을 막아, 관심 종목 회사 IR 페이지 피드로)

kind별 읽기: investis(공시 XML) · rss · dp(Design Portfolio JSON) · html(서버가 그린 뉴스 목록 — 날짜·제목·링크)
robots.txt를 회사마다 지키고(프로젝트 UA·ClaudeBot 둘 다), 원문은 저장하지 않는다 — 제목·링크·분류만(일부 약관의 '개인·내부 사용' 복제 조항).
첫 회차는 기준선만(지난 글을 한꺼번에 보내지 않게), 그 뒤 48시간 안의 새 글만 inbox. 회사 하나가 실패해도 나머지는 읽는다.
사용: py -m pollers.uk_ir [--show]   (radar/에서) — run_poll(10분)이 부른다
"""
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.robotparser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from . import common
from .rss import parse_feed, to_iso

SRC = "src-uk-ir"
STATE = "uk_ir"
LOOKBACK_H = 48
# 정례 공시 — 매일·매주 나오는 자사주 매입 실적·의결권 총수·대량 보유 신고·Form 8.3은 inbox에 넣지 않는다(이사 매매 PDMR는 신호라 남긴다)
ROUTINE = re.compile(r"^(?:Transaction in Own Shares|Total Voting Rights|Holding\(s\) in Company|Block ?listing|Form 8\.3|Form 8 \(OPD\)|Notification of Major Holdings?)", re.I)
_robots = {}


def cfg():
    return (common.load_yaml("config/uk_ir.yaml") or {}).get("companies") or []


def robots_ok(url):
    p = urllib.parse.urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            rp.parse(common.http_get(base + "/robots.txt", timeout=20).decode("utf-8", "ignore").splitlines())
        except Exception:   # 없음·403 → 제한 없음(RFC 9309)
            rp.parse([])
        _robots[base] = rp
    return _robots[base].can_fetch(common.UA, url) and _robots[base].can_fetch("ClaudeBot", url)


def _iso(dt):
    return dt.astimezone(timezone(timedelta(hours=9))).isoformat(timespec="seconds") if dt else ""


def parse_investis(raw):
    root = ET.fromstring(raw.lstrip("﻿").encode("utf-8") if isinstance(raw, str) else raw)
    out = []
    for s in root.iter("RNSSummary"):
        g = lambda k: (s.findtext(k) or "").strip()  # noqa: E731
        try:
            d = parsedate_to_datetime(g("pubDate"))
        except Exception:
            d = None
        out.append({"title": g("Title") or g("Name"), "link": g("ShareURL") or g("Link"), "date": _iso(d), "cat": "RNS"})
    return out


def parse_dp(raw, feed):
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlparse(feed))
    out = []
    for a in json.loads(raw) or []:
        out.append({"title": a.get("title") or "", "link": base + (a.get("url") or ""), "date": a.get("publishedAt") or "", "cat": a.get("category") or "RNS"})
    return out


HTML_RE = re.compile(r'class="news-date">\s*([0-9]{1,2} [A-Z][a-z]+ [0-9]{4})\s*</span>.*?<a[^>]+href="([^"]+)"[^>]*>\s*(.*?)\s*</a>', re.S)


def parse_html(raw, page):
    out = []
    for d, href, title in HTML_RE.findall(raw):
        try:
            dt = datetime.strptime(d, "%d %B %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            dt = None
        out.append({"title": common.strip_tags(title), "link": urllib.parse.urljoin(page, href), "date": _iso(dt), "cat": "news"})
    return out


def parse_rss(raw):
    return [{"title": e["title"], "link": e["link"], "date": to_iso(e["date"]), "cat": "news"} for e in parse_feed(raw)]


def read(co, get=None):
    """→ (회사, 글 목록 또는 None)"""
    get = get or (lambda u: common.http_get(u, headers={"Accept": "application/json"} if co["kind"] == "dp" else None, timeout=30).decode("utf-8", "ignore"))
    try:
        if not robots_ok(co["feed"]):
            return co, None
        raw = get(co["feed"])
        kind = co["kind"]
        rows = (parse_investis(raw) if kind == "investis" else parse_dp(raw, co["feed"]) if kind == "dp"
                else parse_html(raw, co["feed"]) if kind == "html" else parse_rss(raw))
        return co, [r for r in rows if r["link"] and r["title"]]
    except Exception:
        return co, None


def poll(env=None, get=None):
    st = common.load_state(STATE, {})
    seen = set(st.get("seen") or [])
    based = set(st.get("based") or [])
    cutoff = common.now_kst() - timedelta(hours=LOOKBACK_H)
    items, fails = [], []
    cos = cfg()
    with ThreadPoolExecutor(max_workers=6) as ex:
        for co, rows in ex.map(lambda c: read(c, get), cos):
            if rows is None:
                fails.append(co["tidm"])
                continue
            if co["tidm"] not in based:   # 이 회사 첫 회차 — 기준선만
                seen.update(r["link"] for r in rows)
                based.add(co["tidm"])
                continue
            for r in rows[:30]:
                if r["link"] in seen:
                    continue
                seen.add(r["link"])
                if ROUTINE.search(r["title"]):
                    continue
                try:
                    if r["date"] and datetime.fromisoformat(r["date"].replace("Z", "+00:00")) < cutoff:
                        continue
                except ValueError:
                    pass
                items.append(common.make_item(SRC, hashlib.sha1(r["link"].encode()).hexdigest()[:16], r["link"],
                                              f"[RNS] {co['name']}({co['tidm'].rstrip('.')}): {r['title']}", r["date"] or common.iso(common.now_kst()),
                                              "공시" if r["cat"] != "news" else "보도자료", "en", "",
                                              extra={"entities_matched": [co["id"]], "ticker": co["tidm"].rstrip("."), "publisher": co["name"],
                                                     "source_class": "영국 회사 IR 공시(1차)", "rns_category": r["cat"]}))
    st["seen"] = sorted(seen)[-20000:]
    st["based"] = sorted(based)
    st["fails"] = fails
    common.save_state(STATE, st)
    print(f"uk_ir: 회사 {len(cos)} · 읽기 실패 {len(fails)}{(' ' + ','.join(fails)) if fails else ''} · 새 글 {len(items)}")
    return items


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--show" in sys.argv:
        for co in cfg():
            c, rows = read(co)
            print(f"{co['tidm']:5} {co['kind']:8} {'실패' if rows is None else len(rows):>4}  " + (f"{rows[0]['date'][:10]} {rows[0]['title'][:60]}" if rows else ""))
    else:
        print(len(poll()))
