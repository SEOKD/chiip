"""Chiip 해외 법인 — 국내 전자 기업의 해외 법인 소식을 Pulse로 바로 넘긴다
(마스터 지시 2026-11-26 "국내 전자 기업들의 해외 법인 관련 이슈도 즉각 챙겨올 수 있는 정보 파이프라인을 구축하라" — 계기: LG전자 인도법인 지분 2% 추가 매각).

원천(새 유료·키 없음):
  ① 이미 모으는 것: 수집함 radar/inbox/<날짜>/*.json(공시·보도자료·해외 언론), 공개 텔레그램 채널(radar/inbox/tg_channels/), 딘스티커(radar/dticker/posts.jsonl)
  ② 해외 현지 언론 RSS(config/kr_overseas_subs.yaml feeds — robots 허용 확인, 30분에 한 번, 제목·링크·요지만)
  인도 NSE·BSE 공시와 Economic Times는 자동 접근을 막아 쓰지 않는다. 네이버 뉴스 API는 약관(9/7 특약)이 AI 입력·요약을 금지해 쓰지 않는다.
판정: 모회사 이름 + 국가 + '법인·공장·자회사'(영어는 unit·subsidiary·plant·stake…) 또는 법인 고유 이름(Solidigm·Harman·LGEINDIA…).
사용: py radar/overseas_subs.py --scan [시간]   # 지난 n시간(기본 24) 매칭 결과만 보기(상태 안 바꿈)
"""
import html
import json
import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

CFG = common.ROOT / "config" / "kr_overseas_subs.yaml"
STATE = "overseas_subs"
SOURCE_ID = "src-overseas-subs"
ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)


def config():
    return common.load_yaml(CFG)


def _alt(words):
    return "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))


def matcher(cfg=None):
    """text → (모회사 id, 맞은 구절) 또는 None"""
    cfg = cfg or config()
    ck, ce, uk, ue = _alt(cfg["countries_ko"]), _alt(cfg["countries_en"]), _alt(cfg["unit_ko"]), _alt(cfg["unit_en"])
    rules = []
    for s in cfg.get("subsidiaries") or []:
        rules.append((s["parent"], re.compile(r"(?<![A-Za-z])(" + _alt(s["names"]) + r")(?![A-Za-z])")))
    for p in cfg["parents"]:
        rules.append((p["id"], re.compile(r"(" + _alt(p["ko"]) + r")[^\n]{0,6}?(" + ck + r")\s?(" + uk + r")")))
        rules.append((p["id"], re.compile(r"(" + _alt(p["en"]) + r")(?:'s)?[^\n.]{0,40}?\b(" + ce + r")\b[^\n.]{0,30}?\b(" + ue + r")\b", re.I)))

    def match(text):
        for pid, rx in rules:
            m = rx.search(text or "")
            if m:
                return pid, m.group(0)[:80]
        return None
    return match


def _inbox(since):
    days = {since[:10].replace("-", ""), common.now_kst().strftime("%Y%m%d")}
    for d in sorted(days):
        for f in (common.ROOT / "radar" / "inbox" / d).glob("*.json"):
            try:
                x = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if (x.get("detected_at") or "") > since and x.get("source_id") != SOURCE_ID:
                yield {"url": x.get("url"), "title": x.get("title") or "", "text": f"{x.get('title') or ''}\n{x.get('snippet') or ''}",
                       "at": x.get("published_at") or x.get("detected_at"), "seen": x.get("detected_at"), "origin": x.get("source_id")}


def _telegram(since):
    from pollers import tg_channels as tg
    for r in tg.since(since):
        yield {"url": r["url"], "title": r["text"].split("\n")[0][:120], "text": r["text"], "at": r["at"], "seen": r.get("seen"), "origin": f"src-tg-{r['channel']}"}


def _dticker(since):
    import dticker
    for r in dticker.load().values():
        if (r.get("seen") or r.get("at") or "") > since:
            yield {"url": r.get("url"), "title": (r.get("text") or "").split("\n")[0][:120], "text": r.get("text") or "", "at": r.get("at"), "seen": r.get("seen") or r.get("at"), "origin": "src-dticker"}


def parse_rss(xml):
    out = []
    for b in ITEM_RE.findall(xml):
        def tag(t):
            m = re.search(rf"<{t}[^>]*>(.*?)</{t}>", b, re.S)
            return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""
        pub = tag("pubDate")
        try:
            from email.utils import parsedate_to_datetime
            pub = common.iso(parsedate_to_datetime(pub))
        except (TypeError, ValueError):
            pass
        out.append({"title": common.strip_tags(tag("title")), "url": tag("link"), "desc": common.strip_tags(tag("description"))[:300], "pub": pub})
    return out


def _feeds(cfg, st, force=False, sid=SOURCE_ID):
    from datetime import datetime
    now = common.now_kst()
    last = st.get("feeds_at")
    if not force and last and (now - datetime.fromisoformat(last)).total_seconds() < cfg.get("feed_every_min", 30) * 60:
        return
    st["feeds_at"] = common.iso(now)
    ok = True
    for f in cfg.get("feeds") or []:
        try:
            for it in parse_rss(common.http_get(f["url"], timeout=20).decode("utf-8", "ignore")):
                yield {"url": it["url"], "title": it["title"], "text": f"{it['title']}\n{it['desc']}", "at": it["pub"], "seen": common.iso(now), "origin": f"rss-{f['id']}"}
        except Exception:
            ok = False
    common.record_health(sid, ok, None if ok else "RSS 일부 실패")


def scan(since, st=None, cfg=None, feeds=True):
    """since(ISO) 뒤 새 글 중 해외 법인 소식 → Pulse 원본 목록"""
    cfg = cfg or config()
    st = st if st is not None else {}
    match = matcher(cfg)
    seen_urls = set(st.get("urls") or [])
    gens = [_inbox(since), _telegram(since), _dticker(since)] + ([_feeds(cfg, st)] if feeds else [])
    out = []
    for g in gens:
        try:
            for x in g:
                hit = match(x["text"])
                if not hit or not x.get("url") or x["url"] in seen_urls:
                    continue
                seen_urls.add(x["url"])
                out.append({"source_id": SOURCE_ID, "source_class": "해외 법인", "url": x["url"], "title": x["title"][:160], "published_at": x.get("at"),
                            "detected_at": x.get("seen"), "snippet": x["text"][:600], "entities_matched": [hit[0]], "matched": hit[1], "via": x.get("origin")})
        except Exception:
            continue
    st["urls"] = sorted(seen_urls)[-2000:]
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--scan"]:
        h = int(argv[1]) if len(argv) > 1 else 24
        for x in scan(common.iso(common.now_kst() - timedelta(hours=h)), {}):
            print(f"{x['published_at']} [{x['via']}] {x['matched']} — {x['title'][:90]}\n  {x['url']}")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
