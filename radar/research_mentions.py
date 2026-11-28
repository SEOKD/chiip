"""Chiip 리서치 기관 2차 인용 — Omdia·Gartner 발표를 언론 보도로 잡아 Pulse '리서치 기관'으로 넘긴다
(마스터 지시 2026-11-28 "Omdia, Gartner는 언론보도 등 2차 게시글로라도 정보를 수집하도록 하라").

Omdia·Gartner 사이트는 robots는 허용하나 서버가 자동 접근을 403으로 막아(2026-11-28 확인) 직접 읽지 않는다.
원천: ① 이미 모으는 수집함·공개 텔레그램·딘스티커 ② robots 허용을 확인한 언론 RSS(config 아래 FEEDS, 30분에 한 번, 제목·요지만).
The Register·ComputerWeekly·NetworkWorld는 robots가 막아 쓰지 않는다. Google News RSS도 robots 불가.
2차 인용이라 '기관 추정을 언론이 전한 것'이다 — 수치는 1차(기관 발표) 확인 전 미확인.
사용: py radar/research_mentions.py --scan [시간]
"""
import re
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402
import overseas_subs as os_  # noqa: E402   수집함·텔레그램·딘스티커·RSS 읽기를 같이 쓴다

SOURCE_ID = "src-research-mentions"
ORGS = {"omdia": re.compile(r"(?<![A-Za-z])Omdia(?![A-Za-z])|옴디아"), "gartner": re.compile(r"(?<![A-Za-z])Gartner(?![A-Za-z])|가트너")}
FEEDS = [  # 2026-11-28 robots 허용 확인
    {"id": "digitimes", "url": "https://www.digitimes.com/rss/daily.xml"},
    {"id": "etnews", "url": "https://rss.etnews.com/Section901.xml"},
    {"id": "zdnetkr", "url": "https://feeds.feedburner.com/zdkorea"},
    {"id": "thelec", "url": "https://www.thelec.kr/rss/allArticle.xml"},
]
CFG = {"feeds": FEEDS, "feed_every_min": 30}


def match(text):
    for org, rx in ORGS.items():
        m = rx.search(text or "")
        if m:
            return org, text[max(0, m.start() - 30): m.end() + 40].replace("\n", " ")
    return None


def scan(since, st=None, feeds=True):
    st = st if st is not None else {}
    seen = set(st.get("urls") or [])
    fst = st.setdefault("feeds", {})
    gens = [os_._inbox(since), os_._telegram(since), os_._dticker(since)] + ([os_._feeds(CFG, fst, sid=SOURCE_ID)] if feeds else [])
    out = []
    for g in gens:
        try:
            for x in g:
                if x.get("origin") == SOURCE_ID or not x.get("url") or x["url"] in seen:
                    continue
                hit = match(x["text"])
                if not hit:
                    continue
                seen.add(x["url"])
                out.append({"source_id": SOURCE_ID, "source_class": "리서치 기관", "url": x["url"], "title": x["title"][:160],
                            "published_at": x.get("at"), "detected_at": x.get("seen"), "snippet": x["text"][:600],
                            "research_org": hit[0], "research_secondary": True, "matched": hit[1], "via": x.get("origin")})
        except Exception:
            continue
    st["urls"] = sorted(seen)[-2000:]
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--scan"]:
        h = int(argv[1]) if len(argv) > 1 else 24
        for x in scan(common.iso(common.now_kst() - timedelta(hours=h)), {}):
            print(f"{x['published_at']} [{x['via']}] {x['research_org']} — {x['title'][:90]}\n  {x['url']}")
    else:
        print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
