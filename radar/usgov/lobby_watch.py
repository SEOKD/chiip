"""분석 대상 상장사의 로비 내역 조회 (마스터 지시 2026-11-03). 모델 없음

1 연방 로비 공시 LDA(LDA_API_KEY 필요) 2 SEC 공시의 로비 언급 3 언론 제목(비공식 단서).
LDA를 조회하지 못하면 결론은 '미확인'이다. 다른 채널에 없다고 로비가 없다고 쓰지 않는다.
결과: knowledge/models/lobby/<회사 id>.json
사용: py radar/usgov/lobby_watch.py <회사 id> "<공시상 회사명>" [별칭…]
"""
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common  # noqa: E402

OUT = common.ROOT / "knowledge" / "models" / "lobby"
UA = {"User-Agent": "Chiip research fhteo1101@gmail.com"}
FORMS = "DEF 14A,10-K,8-K,20-F"


def fetch(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **(headers or {})}), timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def lda(names, key, year):
    rows = []
    for name in names:
        q = urllib.parse.urlencode({"client_name": name, "filing_year": year, "page_size": 25})
        for r in json.loads(fetch(f"https://lda.gov/api/v1/filings/?{q}", {"Authorization": f"Token {key}"})).get("results", []):
            rows.append({"client": (r.get("client") or {}).get("name"), "registrant": (r.get("registrant") or {}).get("name"), "period": r.get("filing_period_display"), "income": r.get("income"), "expenses": r.get("expenses"), "url": r.get("filing_document_url")})
    return rows


def sec(names):
    rows = []
    for name in names:
        q = urllib.parse.urlencode({"q": f'"{name}" "lobbying"', "forms": FORMS})
        hits = (json.loads(fetch(f"https://efts.sec.gov/LATEST/search-index?{q}")).get("hits") or {}).get("hits", [])
        for h in hits[:10]:
            s = h["_source"]
            rows.append({"form": s.get("form"), "filer": (s.get("display_names") or [""])[0], "date": s.get("file_date"), "id": h["_id"]})
    return rows


def news(names):
    rows = []
    for name in names:
        q = urllib.parse.quote(f'"{name}" lobbying OR lobbyist')
        xml = fetch(f"https://news.google.com/rss/search?q={q}+when:365d&hl=en-US&gl=US&ceid=US:en")
        rows += [{"title": t, "url": u} for t, u in re.findall(r"<item><title>(.*?)</title><link>(.*?)</link>", xml)[:8]]
    return rows


def verdict(doc):
    if doc["lda"]["status"] != "ok":
        return "미확인"
    return "로비 등록 있음" if doc["lda"]["rows"] else "해당 연도 LDA 등록 없음(입력한 이름 기준)"


def _try(fn):
    try:
        return {"status": "ok", "rows": fn()}
    except Exception as e:
        return {"status": f"실패: {type(e).__name__} {e}", "rows": []}


def run(cid, names, today=None):
    today = today or common.now_kst().date()
    key = common.load_env().get("LDA_API_KEY")
    doc = {"company": cid, "names": names, "as_of": today.isoformat(),
           "lda": _try(lambda: lda(names, key, today.year)) if key else {"status": "키 없음", "rows": []},
           "sec": _try(lambda: sec(names)), "news": _try(lambda: news(names))}
    doc["verdict"] = verdict(doc)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{cid}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    d = run(sys.argv[1], sys.argv[2:])
    print(d["verdict"], {k: (d[k]["status"], len(d[k]["rows"])) for k in ("lda", "sec", "news")})
