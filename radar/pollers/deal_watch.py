"""딜 추적 문서철 (마스터 지시 2026-11-12 "Fable 5.2가 조사한 파이프라인을 기사 소재 발굴 시스템에 넣어라")

소문난 딜(예: SK하이닉스–인텔 오하이오 팹 JV)을 미국 1차 문서에서 지켜본다 — 보도 색인, 주·카운티·시 페이지, 시의회 회의 영상의
안건·녹취, 연방 관보, SEC 전문 검색. 설정 config/deal_watch.yaml(문서철마다 키워드·원천·'나타나야 할 서류' 목록).
  새 흔적  → inbox src-deal-watch → Pulse '딜 추적'(기사 소재 1순위 후보, article-pitch가 본다)
  확인 결과 → knowledge/deals/<id>.json — 원천별 마지막 확인 시각·흔적 유무·접근 불가(침묵도 신호, §11.0)
첫 회차는 기준선만(지난 흔적을 한꺼번에 보내지 않는다). 본문 저장 없음 — 제목·링크·키워드가 걸린 문장 앞뒤 200자만.
흔적은 '정황'이다 — 딜 단계(보도·발언·안건·의결·계약)를 구분해 쓴다(금지표: 지방 안건 상정 → 투자 확정).
사용: py -m pollers.deal_watch [--show]   (radar/에서)
"""
import hashlib
import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pollers import common
    from pollers.rss import parse_feed, to_iso
else:
    from . import common
    from .rss import parse_feed, to_iso

SRC = "src-deal-watch"
GN = "https://news.google.com/rss/search"
OUT = common.ROOT / "knowledge" / "deals"


def _h(s):
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def _text(raw):
    """스크립트·스타일·인코딩 데이터(base64 등 긴 토큰)를 걷어낸 본문"""
    raw = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", raw)
    return re.sub(r"\S{60,}", " ", common.strip_tags(raw))


def _snips(text, kw, n=3):
    """키워드가 걸린 문장 앞뒤 200자"""
    out = []
    for m in kw.finditer(text):
        s = re.sub(r"\s+", " ", text[max(0, m.start() - 200): m.end() + 200]).strip()
        if not any(s[:80] in o for o in out):
            out.append(s)
        if len(out) >= n:
            break
    return out


def src_gn(s, kw):
    out = []
    for e in parse_feed(common.http_get(GN, {"q": s["q"] + " when:7d", "hl": "en-US", "gl": "US", "ceid": "US:en"}, timeout=20))[:30]:
        if e["link"]:
            out.append({"key": e["link"], "url": e["link"], "title": common.strip_tags(e["title"]), "at": to_iso(e["date"]), "snip": ""})
    return out


def src_page(s, kw):
    text = _text(common.http_get(s["url"], timeout=30).decode("utf-8", "ignore"))
    return [{"key": _h(x[:160]), "url": s["url"], "title": f"{s['id']} 페이지에 새 문구", "at": None, "snip": x} for x in _snips(text, kw, 6)]


def src_swagit(s, kw):
    out = []
    for body in s["bodies"]:
        lst = common.http_get(s["base"] + body, timeout=30).decode("utf-8", "ignore")
        for vid in list(dict.fromkeys(re.findall(r'/videos/(\d+)', lst)))[:8]:   # 최근 회의 8건(목록은 최신순)
            page = common.http_get(f"{s['base']}/videos/{vid}", timeout=40).decode("utf-8", "ignore")
            text = _text(page)
            title = common.strip_tags(page).strip().split("  ")[0][:80]
            for x in _snips(text, kw, 4):
                out.append({"key": f"{vid}:{_h(x[:160])}", "url": f"{s['base']}/videos/{vid}", "title": f"회의 안건·녹취: {title}", "at": None, "snip": x})
            out.append({"key": f"seen:{vid}", "url": f"{s['base']}/videos/{vid}", "title": title, "at": None, "snip": None})   # 확인한 회의(흔적 없음 기록용)
    return out


def src_fedreg(s, kw):
    d = json.loads(common.http_get("https://www.federalregister.gov/api/v1/documents.json",
                                   {"conditions[term]": s["term"], "order": "newest", "per_page": 20}, timeout=30))
    return [{"key": r["document_number"], "url": r["html_url"], "title": r["title"], "at": r.get("publication_date"), "snip": (r.get("abstract") or "")[:300]}
            for r in d.get("results") or []]


def src_sec_fts(s, kw):
    from pollers import sec_filings
    d = json.loads(common.http_get("https://efts.sec.gov/LATEST/search-index", {"q": s["q"], "forms": s.get("forms", ""), **({"ciks": s["ciks"]} if s.get("ciks") else {})},
                                   headers={"User-Agent": sec_filings._ua()}, timeout=30))
    out = []
    for h in (d.get("hits") or {}).get("hits") or []:
        src = h.get("_source") or {}
        acc = h.get("_id", "").split(":")[0]
        out.append({"key": h.get("_id", ""), "url": f"https://www.sec.gov/Archives/edgar/data/{(src.get('ciks') or [''])[0]}/{acc.replace('-', '')}/",
                    "title": f"{src.get('form', '')} {', '.join(src.get('display_names') or [])[:80]}", "at": src.get("file_date"), "snip": ""})
    return out


KIND = {"gn": src_gn, "page": src_page, "swagit": src_swagit, "fedreg": src_fedreg, "sec_fts": src_sec_fts}


def run_dossier(d, st, now):
    kw = re.compile(d["keywords"], re.I)
    seen = set(st.setdefault(d["id"], {}).get("seen") or [])
    based = set(st[d["id"]].get("based") or [])
    status, items = [], []
    for s in d["sources"]:
        sid = f"{d['id']}:{s['id']}"
        try:
            hits = KIND[s["type"]](s, kw)
        except Exception as e:
            status.append({"source": s["id"], "type": s["type"], "result": "접근 불가", "detail": f"{type(e).__name__}: {str(e)[:80]}", "at": common.iso(now)})
            continue
        new = []
        for h in hits:
            if h["key"] in seen:
                continue
            seen.add(h["key"])
            if h["snip"] is None or sid not in based:
                continue
            if s["type"] == "gn" and not kw.search(h["title"]):   # 구글 검색은 느슨하다 — 제목에 딜 키워드가 있어야(2026-11-12 시험: 소프트뱅크 기사 오탐)
                continue
            new.append(h)
            items.append(common.make_item(SRC, _h(f"{sid}:{h['key']}"), h["url"], f"[딜 추적·{d['title'][:24]}] {h['title'][:140]}",
                                          (h["at"] + "T00:00:00+00:00") if len(str(h.get("at") or "")) == 10 else (h.get("at") or common.iso(now)),
                                          "규제·정책" if s["type"] in ("page", "swagit", "fedreg") else "보도", "en", (h["snip"] or "")[:400],
                                          extra={"entities_matched": d.get("entities") or [], "deal_id": d["id"], "deal_source": s["id"],
                                                 "source_class": f"딜 추적({s['type']}) — 정황, 단계 구분 필요"}))
        based.add(sid)
        hit_n = len([h for h in hits if h["snip"] is not None])
        status.append({"source": s["id"], "type": s["type"], "result": "새 흔적" if new else ("흔적 있음(기존)" if hit_n else "흔적 없음"),
                       "new": len(new), "checked": len(hits), "at": common.iso(now)})
    st[d["id"]] = {"seen": sorted(seen)[-5000:], "based": sorted(based)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{d['id']}.json").write_text(json.dumps({"id": d["id"], "title": d["title"], "stage_note": d.get("stage_note"), "expected": d.get("expected"),
                                                     "blocked": d.get("blocked"), "checked_at": common.iso(now), "sources": status},
                                                    ensure_ascii=False, indent=1), encoding="utf-8")
    return items, status


def poll(env=None):
    cfg = common.load_yaml("config/deal_watch.yaml") or {}
    st, now = common.load_state("deal_watch", {}), common.now_kst()
    items = []
    for d in cfg.get("dossiers") or []:
        items += run_dossier(d, st, now)[0]
    common.save_state("deal_watch", st)
    return items


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    its = poll()
    print(f"deal_watch: 새 흔적 {len(its)}건 · 저장 {len(common.save_new_items(its))}")
    for f in OUT.glob("*.json"):
        d = json.loads(f.read_text(encoding="utf-8"))
        print(d["title"])
        for s in d["sources"]:
            print("  ", s["source"], s["result"], s.get("checked", ""), s.get("detail", ""))
