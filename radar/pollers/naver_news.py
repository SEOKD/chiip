"""네이버 뉴스 검색 API 폴러 — T0 기업명 최신순

규격(키 발급 후 첫 호출로 재확인): GET https://openapi.naver.com/v1/search/news.json
헤더 X-Naver-Client-Id / X-Naver-Client-Secret, 파라미터 query·display(최대 100)·sort=date.
원문은 저장하지 않는다(제목·링크·요지 200자).
"""
import hashlib
import json
from email.utils import parsedate_to_datetime

from . import common

SOURCE_ID = "src-naver-news"
URL = "https://openapi.naver.com/v1/search/news.json"


def poll(env, tiers=("T0",)):
    cid, secret = env.get("NAVER_CLIENT_ID"), env.get("NAVER_CLIENT_SECRET")
    if not cid or not secret:
        raise RuntimeError("NAVER_CLIENT_ID/SECRET 없음")
    headers = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": secret}
    items = []
    for row in common.load_watchlist():
        if row["tier"] not in tiers:
            continue
        query = row["name"].split("(")[0].strip()
        data = json.loads(common.http_get(URL, {"query": query, "display": 30, "sort": "date"}, headers))
        for it in data.get("items", []):
            link = it.get("originallink") or it.get("link")
            try:
                pub = common.iso(parsedate_to_datetime(it["pubDate"]))
            except (KeyError, TypeError, ValueError):
                pub = ""
            items.append(common.make_item(
                SOURCE_ID, hashlib.sha1(link.encode()).hexdigest()[:16], link,
                common.strip_tags(it.get("title")), pub, "기사", "ko", common.strip_tags(it.get("description")),
                extra={"query_entity": row["entity_id"], "tier": row["tier"]}))
    return items
