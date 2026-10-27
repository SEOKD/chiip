"""L8 커뮤니티 — Hacker News(공개 검색 API), Substack RSS, (승인 시) Reddit RSS. 단서 전용(S1).
개인 게시물 장문 저장 금지: 제목·링크·작성 계정(공개 핸들)·200자 요지만.
"""
import json
import time
import urllib.parse
from datetime import timedelta

from common_rev import common, english_names, lexicon, save_candidates

SOURCE_ID = "src-communities"


def run():
    cfg = common.load_yaml("config/community_sources.yaml") or {}
    lex = lexicon()
    cands = []
    if (cfg.get("hacker_news") or {}).get("enabled"):
        since = int((common.now_kst() - timedelta(days=2)).timestamp())
        for eid in lex:
            for name in english_names(eid, lex)[:2]:
                q = {"query": f'"{name}"', "tags": "(story,comment)", "numericFilters": f"created_at_i>{since}",
                     "hitsPerPage": 30}
                data = json.loads(common.http_get(cfg["hacker_news"]["api"], q))
                for h in data.get("hits", []):
                    text = h.get("title") or h.get("comment_text") or ""
                    cands.append({"uid": f"hn:{h['objectID']}", "mentioned_entity": eid, "match_text": name,
                                  "counterparty": f"HN:{h.get('author', '')}", "form": "커뮤니티",
                                  "published_at": h.get("created_at"), "language": "en",
                                  "url": f"https://news.ycombinator.com/item?id={h['objectID']}",
                                  "snippet": common.strip_tags(text)[:200], "signal_type_hint": "커뮤니티"})
                time.sleep(0.3)
    from pollers import rss
    feeds = list((cfg.get("substack") or {}).get("feeds") or [])
    rd = cfg.get("reddit") or {}
    if rd.get("enabled"):
        feeds += [f"https://www.reddit.com/r/{s}/new/.rss" for s in rd.get("subreddits", [])]
    for url in feeds:
        for e in rss.parse_feed(common.http_get(url)):
            text = f"{e['title']} {common.strip_tags(e['desc'])}"
            for eid, info in lex.items():
                hit = next((n for n in info["names"] if n.lower() in text.lower()), None)
                if hit:
                    cands.append({"uid": e["link"], "mentioned_entity": eid, "match_text": hit,
                                  "counterparty": urllib.parse.urlparse(url).netloc, "form": "커뮤니티",
                                  "published_at": rss.to_iso(e["date"]), "language": "en", "url": e["link"],
                                  "snippet": common.strip_tags(e["desc"])[:200], "signal_type_hint": "커뮤니티"})
    n = save_candidates("L8", SOURCE_ID, cands)
    common.record_health(SOURCE_ID, True)
    return len(cands), n


if __name__ == "__main__":
    print("커뮤니티: 후보 %d, 신규 %d" % run())