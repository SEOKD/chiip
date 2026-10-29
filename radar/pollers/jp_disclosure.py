"""일본 정보망 (마스터 지시 2026-10-29 — 이비덴 통기 실적 예상 상향(적시공시)을 놓친 뒤 "일본 정보망도 체계적으로 뚫어라")

config/jp_watch.yaml의 일본 AI 밸류체인 45개사를 Google News 일본판 색인(hl=ja, gl=JP)에서 10분마다 찾는다.
  공시  日経会社情報DIGITAL에 올라오는 적시공시(適時開示) 제목 미러 — '회사[코드]：제목(適時開示)'
  기사  일본 매체 속보(株探·日経·日刊工業 등, jp_watch.yaml publishers만)
TDnet은 robots.txt가 막아 직접 수집하지 않는다. 원문(회사 IR PDF) 확인은 판정·펄스 모델 몫.
회사 6곳씩 묶어 묻고, 100건 상한에 닿으면 반으로 나눠 다시 묻는다(rss.focus7_entries와 같은 이유).
사용: py -m pollers.jp_disclosure   (radar 폴더에서, 1회 수집 결과 출력)
"""
import hashlib
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from . import common
from .rss import GNEWS, parse_feed, to_iso

SOURCE_ID = "src-jp-disclosure"
CHUNK = 6
CAP = 95
_CFG = {}


def cfg():
    if "c" not in _CFG:
        c = common.load_yaml("config/jp_watch.yaml") or {}
        for co in c.get("companies") or []:
            alts = [re.escape(n) for n in co.get("ja") or []] + [re.escape(co["code"]) + r"(?=\]|\b)", r"\b" + re.escape(co["en"]) + r"\b"]
            co["_re"] = re.compile("|".join(alts), re.I)
        c["_pubs"] = {p.lower() for p in c.get("publishers") or []}
        _CFG["c"] = c
    return _CFG["c"]


def _url(companies, window="1d"):
    names = " OR ".join(f'"{n}"' for co in companies for n in (co.get("ja") or [])[:1])
    terms = " OR ".join(cfg().get("event_terms") or [])
    q = f"({names}) ({terms}) when:{window}"
    return GNEWS.format(q=urllib.parse.quote(q), hl="ja", gl="JP").replace("ceid=JP:ja", "ceid=JP:ja")


def entries_for(companies, window="1d"):
    es = parse_feed(common.http_get(_url(companies, window), timeout=30))
    if len(es) >= CAP and len(companies) > 1:
        time.sleep(0.3)
        mid = len(companies) // 2
        seen, out = set(), []
        for e in es + entries_for(companies[:mid], window) + entries_for(companies[mid:], window):
            if e["link"] not in seen:
                seen.add(e["link"])
                out.append(e)
        return out
    return es


def classify(title, publisher):
    """(doc_type, 통과 여부) — 적시공시 미러는 '공시', 일본 매체 기사는 '기사', 그 밖은 버린다"""
    if "適時開示" in title:
        return "공시", True
    if (publisher or "").strip().lower() in cfg()["_pubs"]:
        return "기사", True
    return None, False


def _fresh(iso, hours=36):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")) >= datetime.now(timezone.utc) - timedelta(hours=hours)
    except (AttributeError, ValueError):
        return False


def poll(env=None, window="1d"):
    companies = cfg().get("companies") or []
    items, seen = [], set()
    for i in range(0, len(companies), CHUNK):
        chunk = companies[i:i + CHUNK]
        try:
            entries = entries_for(chunk, window)
        except Exception:
            continue
        for e in entries:
            title = common.strip_tags(e["title"])
            date = to_iso(e["date"])
            if e["link"] in seen or not date or not _fresh(date):
                continue
            hit = next((co for co in companies if co["_re"].search(title)), None)
            if not hit:
                continue
            doc_type, ok = classify(title, e.get("publisher"))
            if not ok:
                continue
            seen.add(e["link"])
            items.append(common.make_item(
                SOURCE_ID, hashlib.sha1(e["link"].encode()).hexdigest()[:16], e["link"], title, date, doc_type, "ja",
                common.strip_tags(e.get("desc") or "")[:300],
                extra={"entities_matched": [hit["id"]], "publisher": (e.get("publisher") or "").strip(), "tier": "일본",
                       "jp_code": hit["code"], "company_en": hit["en"]}))
        time.sleep(0.5)
    return items


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    its = poll()
    print(f"일본 {len(its)}건")
    for it in its[:30]:
        print("-", it["published_at"][:16], it["doc_type"], it.get("publisher"), it["title"][:90])
