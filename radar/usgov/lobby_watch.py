"""분석 대상 상장사의 로비 내역 조회 (마스터 지시 2026-11-03). 모델 없음

1 연방 로비 공시 LDA(LDA_API_KEY 필요 — 2026-11-08 lda.gov가 한국 접속을 막아 보류) 2 SEC 공시의 로비 언급 3 언론 제목(비공식 단서)
4 하원 LD 공시 분기 집계(Easyconomics insider_and_politics section=lobbying — MCP라 모델이 받아 --put-house로 넣는다, 2026-11-08 마스터 지시 "연결해").
LDA와 하원 집계가 모두 없으면 결론은 '미확인'이다. 다른 채널에 없다고 로비가 없다고 쓰지 않는다. 하원 집계는 대형주 약 120개만 다룬다.
결과: knowledge/models/lobby/<회사 id>.json
사용: py radar/usgov/lobby_watch.py <회사 id> "<공시상 회사명>" [별칭…]
      py radar/usgov/lobby_watch.py --put-house <회사 id> <티커> <Easyconomics 출력 파일>
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
UA = {"User-Agent": common.UA}
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
    h = doc.get("house") or {}
    if h.get("status") == "ok":   # 하원 LD 분기 집계 — 금액이 있으면 로비 등록이 있다는 뜻
        return "로비 지출 있음(하원 LD 분기 집계)" if any((r.get("total_usd") or 0) > 0 for r in h["rows"]) else "최근 분기 하원 LD 지출 없음"
    if doc["lda"]["status"] != "ok":
        return "미확인"
    return "로비 등록 있음" if doc["lda"]["rows"] else "해당 연도 LDA 등록 없음(입력한 이름 기준)"


def house_rows(mcp, ticker):
    """Easyconomics lobbying 출력 → 분기 행. 이 티커가 유니버스 밖이면 None"""
    if (mcp.get("ticker") or "").upper() != ticker.upper() or not mcp.get("quarters"):
        return None
    return [{"year": q.get("year"), "quarter": q.get("quarter"), "total_usd": q.get("total_usd"), "self_reported": q.get("self_reported"),
             "outside_income": q.get("outside_income"), "issues": [f"{c['code']} {c['count']}" for c in q.get("top_issue_codes") or []]}
            for q in mcp["quarters"]]


def put_house(cid, ticker, path, today=None):
    """하원 LD 분기 집계를 그 회사 로비 장부에 붙인다. 다른 채널 결과는 그대로 둔다"""
    text = Path(path).read_text(encoding="utf-8")
    mcp = json.loads(text[text.index("{"):text.rindex("}") + 1])
    f = OUT / f"{cid}.json"
    doc = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"company": cid, "names": [], "lda": {"status": "키 없음", "rows": []},
                                                                         "sec": {"status": "미조회", "rows": []}, "news": {"status": "미조회", "rows": []}}
    rows = house_rows(mcp, ticker)
    doc["house"] = ({"status": "ok", "source": f"Easyconomics {mcp.get('source', 'house_ld')}", "as_of": mcp.get("as_of"), "rows": rows} if rows else
                    {"status": "유니버스 밖", "source": "Easyconomics house_ld", "as_of": mcp.get("as_of"), "rows": []})
    doc["verdict"] = verdict(doc)
    OUT.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


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
    prev = OUT / f"{cid}.json"
    if prev.exists():   # 모델이 넣은 하원 LD 집계는 다시 돌려도 남긴다
        h = json.loads(prev.read_text(encoding="utf-8")).get("house")
        if h:
            doc["house"] = h
    doc["verdict"] = verdict(doc)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{cid}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["--put-house"]:
        d = put_house(sys.argv[2], sys.argv[3], sys.argv[4])
        print(d["verdict"], d["house"]["status"], len(d["house"]["rows"]))
        sys.exit(0)
    d = run(sys.argv[1], sys.argv[2:])
    print(d["verdict"], {k: (d[k]["status"], len(d[k]["rows"])) for k in ("lda", "sec", "news")})
