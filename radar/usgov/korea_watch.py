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
UA = {"User-Agent": "Mozilla/5.0 (compatible; Chiip research; fhteo1101@gmail.com)"}
LINK = re.compile(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
DOC = re.compile(r"\.pdf|minutes|agenda|board-?material", re.I)


def fetch(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **(headers or {})}), timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def page_docs(html, base, terms):
    """목록 페이지의 문서 링크"""
    out = {}
    for href, text in LINK.findall(html):
        if DOC.search(href) or DOC.search(text):
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
        for title, link in re.findall(r"<item><title>(.*?)</title><link>(.*?)</link>", xml)[:8]:
            rows.append({"type": "언론 제목", "query": q, "title": title, "url": link})
    return rows


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
            old = set(seen.get(p["id"], []))
            docs = page_docs(fetch(p["url"]), p["url"], cfg["page_terms"])
            rows += [{"type": "회의 자료", "juris": p["juris"], **d} for d in docs if d["url"] not in old]
            seen[p["id"]] = sorted(old | {d["url"] for d in docs})
        except Exception as e:
            errors.append(f"{p['id']}: {type(e).__name__} {e}")
    common.save_state("korea_watch", seen)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"as_of": today.isoformat(), "rows": rows, "errors": errors}, ensure_ascii=False, indent=1), encoding="utf-8")
    if not rows and len(errors) > 1:
        raise RuntimeError("한국 기업 추적 실패: " + "; ".join(errors[:3]))
    return f"단서 {len(rows)}건, 오류 {len(errors)}건"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(run())
    print("\n".join(json.loads(OUT.read_text(encoding="utf-8"))["errors"]))
