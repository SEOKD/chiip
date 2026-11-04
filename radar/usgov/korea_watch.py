"""한국 기업의 미국 상장·로비·지방 안건과 해외 M&A·전략 투자 단서 수집 (마스터 지시 2026-11-03). 모델 없음, 판단은 Chiip Report 회차

SEC 전문 검색, 연방 로비 공시(LDA_API_KEY 필요), 뉴욕·오하이오 기관 회의 자료 목록, 언론 제목. 모두 공개 자료이고 개인 취재 내용은 넣지 않는다.
결과: knowledge/models/korea_watch/latest.json. 항목은 단서이며 사실이 아니다.
사용: py radar/usgov/korea_watch.py
"""
import datetime
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

OUT = common.ROOT / "knowledge" / "models" / "korea_watch" / "latest.json"
UA = {"User-Agent": common.UA}
LINK = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
DOC = re.compile(r"\.pdf|minutes|agenda|board-?material", re.I)
JUNK = re.compile(r"mailto:|email-protection|cdn-cgi|/tag/|/category/|#", re.I)


def fetch(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **(headers or {})}), timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def page_docs(html, base, terms, mode="docs"):
    """목록 페이지의 문서 링크. mode news = 보도자료 목록 — 문서 형식과 무관하게 감시어가 든 링크만(2026-11-04)"""
    out = {}
    for href, text in LINK.findall(html):
        label = re.sub(r"\s+", " ", common.strip_tags(text)).strip()
        if mode == "news" and (JUNK.search(href) or len(label) < 25):   # 메뉴·이메일 보호·짧은 탐색 링크(2026-11-04 첫 실행 잡음)
            continue
        hit = any(t.lower() in f"{label} {href}".lower() for t in terms)
        if (mode == "news" and hit) or (mode != "news" and (DOC.search(href) or DOC.search(text))):
            url = urllib.parse.urljoin(base, href)
            title = re.sub(r"\s+", " ", common.strip_tags(text)).strip()
            out[url] = {"url": url, "title": title, "terms": [t for t in terms if t.lower() in f"{title} {href}".lower()]}
    return list(out.values())


def edgar(cfg, today):
    start = (today - datetime.timedelta(days=cfg["days"])).isoformat()
    rows = []
    for names in cfg["companies"].values():
        for name in names:
            q = urllib.parse.urlencode({"q": f'"{name}"', "forms": cfg["edgar_forms"], "startdt": start, "enddt": today.isoformat()})
            for h in (json.loads(fetch(f"https://efts.sec.gov/LATEST/search-index?{q}")).get("hits") or {}).get("hits", [])[:10]:
                s = h["_source"]
                rows.append({"type": "SEC", "match": name, "form": s.get("form"), "filer": (s.get("display_names") or [""])[0], "date": s.get("file_date"), "id": h["_id"]})
    return rows


def lda(cfg, today, key):
    rows = []
    for names in cfg["companies"].values():
        for name in names:
            q = urllib.parse.urlencode({"client_name": name, "filing_year": today.year, "page_size": 10})
            for r in json.loads(fetch(f"https://lda.gov/api/v1/filings/?{q}", {"Authorization": f"Token {key}"})).get("results", []):
                rows.append({"type": "로비", "match": name, "client": r.get("client", {}).get("name"), "registrant": r.get("registrant", {}).get("name"), "period": r.get("filing_period_display"), "income": r.get("income"), "url": r.get("filing_document_url")})
    return rows


def news(cfg):
    rows = []
    for q in cfg["news"]:
        lang = "hl=ko&gl=KR&ceid=KR:ko" if re.search("[가-힣]", q) else "hl=en-US&gl=US&ceid=US:en"
        xml = fetch(f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}+when:14d&{lang}")
        for title, link, rest in re.findall(r"<item><title>(.*?)</title><link>(.*?)</link>(.*?)</item>", xml, re.S)[:8]:
            m = re.search(r"<pubDate>(.*?)</pubDate>", rest)
            rows.append({"type": "언론 제목", "query": q, "title": title, "url": link, "pub": m.group(1) if m else None})
    return rows


def to_items(rows, cfg):
    """Pulse가 보도록 radar inbox 항목으로(2026-11-04 마스터 지시 "SK하이닉스 관련 공시와 연방·주·시 정부 자료를 시의성 있게").
    회의 자료·보도자료 = 이름이 일치한 새 문서만 src-policy-us-kw(Pulse '정부' 유형) · 언론 제목 = 감시 회사 이름이 제목에 있는 것만 src-kw-news(빠른 길·판정 몫)"""
    import email.utils
    import hashlib
    names = [n for ns in cfg["companies"].values() for n in ns]
    out = []
    for r in rows:
        if r["type"] == "회의 자료" and r.get("terms"):
            title = f"[{r['juris']}] {r['title'] or r['url'].rsplit('/', 1)[-1]}"
            out.append(common.make_item("src-policy-us-kw", hashlib.sha1(r["url"].encode()).hexdigest()[:16], r["url"], title,
                                        common.iso(common.now_kst()), "정부", "en", "일치: " + ", ".join(r["terms"]),
                                        extra={"juris": r["juris"], "published_estimated": True}))
        elif r["type"] == "언론 제목" and any(n.lower() in r["title"].lower() for n in names):
            try:
                pub = common.iso(email.utils.parsedate_to_datetime(r["pub"]).astimezone(common.KST)) if r.get("pub") else None
            except (TypeError, ValueError):
                pub = None
            out.append(common.make_item("src-kw-news", hashlib.sha1(r["url"].encode()).hexdigest()[:16], r["url"], common.strip_tags(r["title"]),
                                        pub, "기사", "ko" if re.search("[가-힣]", r["title"]) else "en", "", extra={"query": r["query"]}))
    return out


def run(today=None):
    today = today or common.now_kst().date()
    cfg = common.load_yaml("config/us_gov/korea_watch.yaml")
    key = common.load_env().get("LDA_API_KEY")
    seen = common.load_state("korea_watch", {})
    rows, errors = [], []
    for name, fn in (("SEC", lambda: edgar(cfg, today)), ("언론", lambda: news(cfg)), ("로비", (lambda: lda(cfg, today, key)) if key else None)):
        if fn is None:
            errors.append("로비: LDA_API_KEY 없음")
            continue
        try:
            rows += fn()
        except Exception as e:
            errors.append(f"{name}: {type(e).__name__} {e}")
    for p in cfg["pages"]:
        try:
            first = p["id"] not in seen   # 처음 보는 페이지는 기준선만 기록(전부 '새 문서'로 내보내지 않는다)
            old = set(seen.get(p["id"], []))
            terms = cfg.get("news_terms") or cfg["page_terms"] if p.get("mode") == "news" else cfg["page_terms"]
            docs = page_docs(fetch(p["url"]), p["url"], terms, p.get("mode", "docs"))
            if not first:
                rows += [{"type": "회의 자료", "juris": p["juris"], **d} for d in docs if d["url"] not in old]
            seen[p["id"]] = sorted(old | {d["url"] for d in docs})
        except Exception as e:
            errors.append(f"{p['id']}: {type(e).__name__} {e}")
    common.save_state("korea_watch", seen)
    new = common.save_new_items(to_items(rows, cfg))   # Pulse·빠른 길이 보도록(2026-11-04)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"as_of": today.isoformat(), "rows": rows, "errors": errors}, ensure_ascii=False, indent=1), encoding="utf-8")
    if not rows and len(errors) > 1:
        raise RuntimeError("한국 기업 추적 실패: " + "; ".join(errors[:3]))
    return f"단서 {len(rows)}건, inbox 신규 {len(new)}건, 오류 {len(errors)}건", len(new)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(run()[0])
    print("\n".join(json.loads(OUT.read_text(encoding="utf-8"))["errors"]))
