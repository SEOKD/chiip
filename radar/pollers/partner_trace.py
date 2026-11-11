"""협업 흔적 공식 자료 감시 (마스터 지시 2026-11-11 "1, 2, 3 모두 구현해")

링크드인 이력(제외 원천·신원 추적 금지) 대신 회사가 공식으로 공개한 자료에서 삼성전자·SK하이닉스 협업 흔적을 찾는다.
  ① 협업사 공식 채널(EDA·IP·칩·하이퍼스케일러·후공정·장비 뉴스룸·기술 블로그·학회 프로그램) — 사이트를 한정한 Google News RSS 검색
  ② 블로그 판정 표(outputs/report/20261111_gamma_partnership_claims.md)의 미확인 주장 — 공개 근거가 나오면 알린다
config/partner_trace.yaml. 새 글(lookback_h 안, 처음 보는 링크)만 inbox src-partner-trace → Pulse '협업 흔적'. 첫 회차는 기준선만.
원문은 저장하지 않는다(제목·링크·발행시각). 협업 발표는 매출 확정이 아니다(금지표 '협력·MOU → 매출 확보').
사용: py -m pollers.partner_trace   (radar/에서)  /  run_poll 30분
"""
import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pollers import common
    from pollers.rss import parse_feed, to_iso
else:
    from . import common
    from .rss import parse_feed, to_iso

SRC = "src-partner-trace"
GN = "https://news.google.com/rss/search"


def queries(cfg):
    """[(질의 id, 검색어, entity, 이유)]"""
    out = []
    for p in cfg.get("partners") or []:
        sites = " OR ".join(f"site:{s}" for s in p["sites"])
        for eid, terms in (cfg.get("entity_terms") or {}).items():
            out.append((f"{p['id']}:{eid}", f"({terms}) ({sites})", eid, p["why"]))
    for c in cfg.get("claims") or []:
        out.append((f"claim:{c['id']}", c["q"], c["entity"], c["why"]))
    return out


def poll(env=None):
    cfg = common.load_yaml("config/partner_trace.yaml") or {}
    st = common.load_state("partner_trace", {})
    seen, based = set(st.get("seen") or []), set(st.get("based") or [])
    cutoff = common.now_kst() - timedelta(hours=cfg.get("lookback_h", 48))
    items, errs = [], []
    for qid, q, eid, why in queries(cfg):
        try:
            entries = parse_feed(common.http_get(GN, {"q": q + " when:7d", "hl": "en-US", "gl": "US", "ceid": "US:en"}, timeout=20))
        except Exception as e:
            errs.append(f"{qid} {type(e).__name__}")
            continue
        for e in entries[:30]:
            if not e["link"] or e["link"] in seen:
                continue
            seen.add(e["link"])
            pub = to_iso(e["date"])
            if qid not in based or (pub and datetime.fromisoformat(pub) < cutoff):
                continue
            items.append(common.make_item(SRC, hashlib.sha1(e["link"].encode()).hexdigest()[:16], e["link"],
                                          f"[협업 흔적] {common.strip_tags(e['title'])}", pub or common.iso(common.now_kst()), "보도자료", "en",
                                          why, extra={"entities_matched": [eid], "trace_query": qid, "source_class": "협업사 공식 자료·학회(Google News 색인)"}))
        based.add(qid)
    st.update({"seen": list(seen)[-20000:], "based": sorted(based)})
    common.save_state("partner_trace", st)
    if errs and len(errs) == len(queries(cfg)):
        raise RuntimeError("; ".join(errs[:3]))
    return items


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    its = poll()
    print(f"partner_trace: 새 글 {len(its)}건 · 저장 {len(common.save_new_items(its))}")
    for it in its[:10]:
        print(" ", it["title"][:110])
