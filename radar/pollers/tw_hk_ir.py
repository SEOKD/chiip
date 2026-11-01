"""대만·홍콩 IR 문서 수집 (마스터 지시 2026-11-01 "대만, 홍콩 상장주식도 일본처럼 회사의 공식 IR 사이트에서 Q&A Summary와 Earning Calls Script를 찾는 파이프라인을 구성해라. 비공식 채널도 찾아와라")

공식 경로: config/tw_hk_ir.yaml 회사 프로필의 자료실을 읽는다. 자료실이 비어 있으면 jp_ir_docs.deep_pages로 찾는다. 판별은 일본과 같은 코드에 회사별 kinds·중문 규칙을 더한다.
비공식 경로: StockAnalysis 공개 전사 목록(/quote/tpe/{코드}/transcripts/, /quote/hkg/{코드}/transcripts/). 새 분기가 보이면 C등급으로 싣는다. 유료 구역은 열지 않는다.
읽은 문서는 IR 처리 장부(radar/ir_ledger.py)를 거쳐 Pulse가 분석한다. robots·요청 간격은 jp_ir_qa.fetch를 따른다.
사용: py radar/pollers/tw_hk_ir.py --discover   # 자료실을 찾아 상태에 넣고 경로표를 쓴다
"""
import argparse
import csv
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common, jp_ir_docs as docs, jp_ir_qa as qa  # noqa: E402

SRC_QA, SRC_DOC = "src-tw-hk-ir-qa", "src-tw-hk-ir-docs"
STATE = "tw_hk_ir"
CACHE = common.ROOT / "radar" / "inbox" / "tw_hk_qa"
ROUTES = common.ROOT / "knowledge" / "models" / "earnings" / "tw_hk_ir_routes.csv"
KINDS = {"transcript": r"逐字稿|法說會紀錄|會議紀錄|transcript|management report|with script",
         "qa": r"問答|问答|Q&A|FAQ for|常見問題.*法說",
         "presentation": r"法說會簡報|法人說明會簡報|簡報|投影片|业绩演示|業績簡報|業績發布|earnings (conference|presentation|release)|investor (conference|presentation)|presentation",
         "tanshin": r"財務報告|财务报告|financial (report|statements)|results announcement|interim report|annual results|業績公告|业绩公告"}
QA_KINDS = ("transcript", "qa")
PERIOD_RES = (re.compile(r"(?<![0-9A-Za-z])([1-4])Q(\d\d)(?![0-9])", re.I), re.compile(r"(20\d\d)\s*年?\s*第?\s*([一二三四1-4])\s*季"), re.compile(r"(20\d\d)\s*[_\- ]?\s*Q([1-4])", re.I))
CN_Q = {"一": 1, "二": 2, "三": 3, "四": 4}


def config():
    return common.load_yaml("config/tw_hk_ir.yaml")


def profile(c):
    """일본 코드가 읽는 프로필 모양으로 — 회사 kinds가 공통 규칙보다 먼저"""
    return {"langs": ["ja", "en"], "kinds": {**KINDS, **(c.get("kinds") or {})}}


def period(title, url):
    """'3Q26'·'2026 Q3'·'2026年第三季' → 'FY2026Q3'. 못 읽으면 일본 규칙으로"""
    for hay in (docs._z(title), docs.urllib.parse.unquote(url)):
        for i, rx in enumerate(PERIOD_RES):
            m = rx.search(hay)
            if m:
                a, b = m.group(1), m.group(2)
                return f"FY20{b}Q{a}" if i == 0 else f"FY{a}Q{CN_Q.get(b, b)}"
    return docs.period_of(title, url)


def scan(html_text, base, c):
    rows = docs.scan_docs(html_text, base, profile(c))
    for d in rows:
        d["period"] = period(d["title"], d["url"]) or d["period"]
    return rows


def fresh_docs(rows, today, fresh_days=21):
    """이번 실적 문서만 — 날짜가 있으면 fresh_days일 안, 없으면 페이지의 최신 기간"""
    limit = str(today.year + 1)
    periods = [d["period"] for d in rows if d["period"] and d["period"][2:6] <= limit]
    latest = max(periods, default=None)
    out = []
    for d in rows:
        if d["date"]:
            if (today - docs.date.fromisoformat(d["date"])).days <= fresh_days:
                out.append(d)
        elif d["period"] and d["period"] == latest:
            out.append(d)
    return out


def _item(cid, c, d, text, path):
    source = SRC_QA if d["kind"] in QA_KINDS else SRC_DOC
    extra = {"entities_matched": [cid], "publisher": c.get("name"), "kind": d["kind"], "period": d["period"], "doc_date": d["date"], "local_text": path, "chars": len(text),
             "grade": d.get("grade", "A"), "tier": "전문·스크립트" if d["kind"] == "transcript" else "Q&A" if d["kind"] == "qa" else d["kind"], "lang": c.get("market")}
    return common.make_item(source, hashlib.sha1(d["key"].encode()).hexdigest()[:16], d["url"], f"{c.get('name')} IR: {d['title'][:80]}", common.iso(common.now_kst()),
                            "IR 질의응답" if d["kind"] in QA_KINDS else "IR 자료", "en", f"{d['kind']} · {d['period'] or '기간 미확인'} · 글자 {len(text)}", extra=extra)


def save_text(cid, d, text):
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{cid}_{d['kind']}_{d['period'] or 'na'}_{hashlib.sha1(d['key'].encode()).hexdigest()[:8]}.txt"
    p.write_text(f"出典: {d['url']}\n資料: {d['title']}\n\n{text}", encoding="utf-8")
    return str(p.relative_to(common.ROOT))


def official(cid, c, cs, today, items, first):
    pages = c.get("doc_pages") or cs.get("doc_pages") or []
    rows, seen = [], set(cs.get("seen") or [])
    for pg in pages:
        rows += scan(qa._text(qa.fetch(pg)), pg, c)
    new = [d for d in rows if d["key"] not in seen and d["kind"] != "video"]
    keep = {d["key"] for d in fresh_docs(rows, today)}
    for d in new:
        seen.add(d["key"])
        if first or d["key"] not in keep:   # 첫 회차와 과거 자료는 기록만
            continue
        text = qa.to_text(d["url"], qa.fetch(d["url"], 60))
        items.append(_item(cid, c, d, text, save_text(cid, d, text)))
    cs["seen"] = sorted(seen)[-500:]


def transcript_links(page):
    return sorted(set(re.findall(r'href="(/quote/(?:tpe|hkg)/[^"/]+/transcripts/(\d+-q([1-4])-(20\d\d))/?)"', page)) | set(re.findall(r'(/transcripts/(\d+-q([1-4])-(20\d\d)))', page)), key=lambda x: (x[3], x[2]))


def unofficial(cid, c, cs, items, first):
    """StockAnalysis 공개 전사 목록 — 가장 최근 분기만 본다"""
    market = {"tw": "tpe", "hk": "hkg"}[c["market"]]
    code = str(c["code"]).zfill(4)
    links = transcript_links(qa._text(qa.fetch(f"https://stockanalysis.com/quote/{market}/{code}/transcripts/")))
    if not links:
        return
    href, slug, q, y = links[-1]
    tag = f"FY{y}Q{q}"
    if cs.get("sa_latest") == tag:
        return
    cs["sa_latest"] = tag
    if first:
        return
    url = f"https://stockanalysis.com{href}"
    d = {"key": url, "url": url, "title": f"{tag} earnings call transcript (StockAnalysis, 제3자 전사)", "kind": "transcript", "period": tag, "date": "", "grade": "C"}
    text = qa.to_text(url, qa.fetch(url, 40))
    if len(text) > 2000:   # 유료 구역이면 본문이 짧다 — 없는 것으로 친다
        items.append(_item(cid, c, d, text, save_text(cid, d, text)))


def poll(env=None):
    st = common.load_state(STATE, {"companies": {}})
    today = common.now_kst().date()
    items, errors = [], []
    for cid, c in (config().get("companies") or {}).items():
        cs = st["companies"].setdefault(cid, {"seen": []})
        first = not cs.get("baselined")
        for fn, args in ((official, (cid, c, cs, today, items, first)), (unofficial, (cid, c, cs, items, first))):
            try:
                fn(*args)
            except Exception as exc:
                errors.append(f"{cid}: {fn.__name__} {type(exc).__name__}")
        cs["baselined"] = True
    st["errors"] = errors
    common.save_state(STATE, st)
    return items


def discover():
    """자료실을 찾아 상태에 넣고 회사별 경로표를 쓴다"""
    st = common.load_state(STATE, {"companies": {}})
    rows = []
    for cid, c in (config().get("companies") or {}).items():
        cs = st["companies"].setdefault(cid, {"seen": []})
        site = c["site"].rstrip("/")
        starts = list(c.get("ir_pages") or []) or [site + p for p in ("/investors/", "/investor/", "/ir/", "/en/investors/", "/zh-TW/investors/")]
        pages, note = list(c.get("doc_pages") or []), ""
        if not pages:
            try:
                pages = deep(starts, c)
            except Exception as exc:
                note = type(exc).__name__
        if pages:
            cs["doc_pages"] = pages
        count = 0
        for pg in pages:
            try:
                count += len(scan(qa._text(qa.fetch(pg)), pg, c))
            except Exception as exc:
                note = type(exc).__name__
        rows.append({"id": cid, "market": c["market"], "route": "회사 자료실" if count else "자료실 미확인", "pages": ";".join(pages), "docs": count, "note": note})
        print(cid, rows[-1]["route"], count, pages[:1], note, flush=True)
        common.save_state(STATE, st)
    ROUTES.parent.mkdir(parents=True, exist_ok=True)
    with ROUTES.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id", "market", "route", "pages", "docs", "note"])
        w.writeheader()
        w.writerows(rows)
    return rows


def deep(starts, c, budget=20):
    """IR 경로 안을 훑어 문서 링크가 가장 많은 페이지를 고른다"""
    queue, seen, scored, n = list(starts), set(), {}, 0
    while queue and n < budget:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            h = qa._text(qa.fetch(url))
            n += 1
        except Exception:
            continue
        rows = [d for d in scan(h, url, c) if d["kind"] != "video"]
        if rows:
            scored[url] = len(rows)
        for u, t in qa.links(h, url):
            if re.search(r"invest|ir/|ir$|法說|法人|投資人|投资者|財務|業績|presentation|conference|results|report", f"{u} {t}", re.I) and not docs.DOC_RE.search(u) and u not in seen:
                queue.append(u)
    return sorted(scored, key=lambda u: -scored[u])[:3]


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true")
    a = ap.parse_args(argv)
    if a.discover:
        rows = discover()
        print("자료실", sum(1 for r in rows if r["docs"]), "/", len(rows))
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
