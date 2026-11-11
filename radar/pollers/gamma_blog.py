"""감마의 하드웨어정보(gamma0burst.tistory.com) '단신 > 단신' 새 글 감시 (마스터 지시 2026-11-11 "이 블로그에 단신에 글이 올라오면 Pulse로 즉시 알려주는 파이프라인")

블로그 공식 RSS(https://gamma0burst.tistory.com/rss, robots 허용 2026-11-11 확인)에서 분류가 '단신/단신'인 글만 받는다. 10분마다(run_poll).
본문은 저장하지 않는다(제목·링크·게시 시각·요약 앞부분). 글쓴이가 스스로 2차 출처라 밝힌 블로그 — 커뮤니티 신호(S1·S2)이지 주장이 아니다.
글 속 이력 그림의 원본(개인 프로필)을 찾지 않는다(2026-11-11 마스터와 합의). 주장 판정은 outputs/report/20261111_gamma_partnership_claims.md 방식.
사용: py -m pollers.gamma_blog   (radar/에서)
"""
import hashlib
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pollers import common
    from pollers.rss import to_iso
else:
    from . import common
    from .rss import to_iso

SRC = "src-gamma-blog"
RSS = "https://gamma0burst.tistory.com/rss"
CATEGORY = "단신/단신"


def entries(raw):
    """[{title, link, date, category, desc}] — 분류를 같이 읽으려고 RSS를 직접 푼다"""
    out = []
    for it in re.findall(r"<item>(.*?)</item>", raw, re.S):
        g = lambda tag: (re.search(rf"<{tag}>(.*?)</{tag}>", it, re.S) or [None, ""])[1]
        strip = lambda x: re.sub(r"^<!\[CDATA\[|\]\]>$", "", x.strip())
        out.append({"title": strip(g("title")), "link": strip(g("link")), "date": strip(g("pubDate")),
                    "category": strip(g("category")), "desc": common.strip_tags(strip(g("description")))})
    return out


def poll(env=None):
    raw = common.http_get(RSS, timeout=20).decode("utf-8", "ignore")
    items = []
    for e in entries(raw):
        if e["category"] != CATEGORY or not e["link"]:
            continue
        items.append(common.make_item(SRC, hashlib.sha1(e["link"].encode()).hexdigest()[:16], e["link"], f"[감마 단신] {e['title']}",
                                      to_iso(e["date"]), "블로그", "ko", e["desc"][:400],
                                      extra={"source_class": "개인 블로그(2차 출처·루머 포함, S1·S2 신호)"}))
    return items


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for it in poll():
        print(it["published_at"][:16], it["title"])
