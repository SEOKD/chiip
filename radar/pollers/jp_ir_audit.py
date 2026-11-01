"""일본 IR 커버리지 점검 (마스터 지시 2026-11-01 "일본 상장회사의 어닝콜 트랜스크립트 및 스크립트, Q&A 스크립트 등을 회사 공식 IR 사이트에서 접근하는 구조를 다시 점검")

회사마다 자료실을 찾았는지, 최신 기간의 PT·단신·전문·Q&A가 있는지, 어디서 막혔는지 표로 만든다. --live는 실제 페이지를 읽고, 새로 찾은 자료실을 수집기 상태에 넣는다.
저장: knowledge/models/earnings/jp_ir_coverage.csv
사용: py radar/pollers/jp_ir_audit.py [--live]
"""
import argparse
import csv
import sys
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pollers import common, jp_ir_docs as docs, jp_ir_qa  # noqa: E402

OUT = common.ROOT / "knowledge" / "models" / "earnings" / "jp_ir_coverage.csv"
FIELDS = ["id", "doc_pages", "latest_period", "presentation", "tanshin", "transcript", "qa", "qa_format", "external", "state"]


def row(cid, cfg, d, q, prof, pages=None, docs_found=None, year=None):
    """pages·docs_found를 주면 실제 페이지를 스캔한 결과로, 없으면 수집기 상태로 판정한다"""
    found = {}
    if docs_found is None:
        docs_found = [{"kind": docs.kind_of(unquote(u.rsplit("/", 1)[-1]), u), "period": docs.period_of(unquote(u.rsplit("/", 1)[-1]), u)} for u in list(d.get("seen") or []) + list(q.get("seen") or [])]
    for x in docs_found:
        if x["kind"] and x["period"] and x["period"][2:6] <= str((year or 2100) + 1):
            found.setdefault(x["period"], set()).add(x["kind"])
    latest = max(found, default="")
    have = found.get(latest, set())
    n = len(pages) if pages is not None else len(cfg.get("doc_pages") or d.get("doc_pages") or [])
    if not n:
        state = "자료실 미발견"
    elif not latest:
        state = "기간 판독 실패"
    elif "transcript" in have or "qa" in have:
        state = "전문·Q&A 있음"
    else:
        state = "전문·Q&A 없음"
    return {"id": cid, "doc_pages": n, "latest_period": latest, "presentation": "presentation" in have, "tanshin": "tanshin" in have, "transcript": "transcript" in have,
            "qa": "qa" in have, "qa_format": prof.get("qa_format") or "", "external": ";".join(prof.get("external") or []), "state": state}


def table():
    cfg = (common.load_yaml("config/jp_ir.yaml") or {}).get("companies") or {}
    d, q = common.load_state("jp_ir_docs", {"companies": {}})["companies"], common.load_state("jp_ir_qa", {"companies": {}})
    prof = q.get("profiles") or {}
    return [row(cid, c, d.get(cid) or {}, (q.get("companies") or {}).get(cid) or {}, prof.get(cid) or {}, year=common.now_kst().year) for cid, c in cfg.items()]


def starts(c, q):
    """깊은 탐색의 출발점 — 수집기가 찾은 IR 페이지, 없으면 대표 경로"""
    out = list(c.get("ir_pages") or []) + list(q.get("pages") or [])
    return out or [c["site"].rstrip("/") + p for p in ("/ir/", "/jp/ir/", "/ja/ir/")]


def live_row(cid, c, d, q, prof, budget=25, year=None):
    """실제 페이지를 읽어 판정한다. 찾은 자료실은 pages로 돌려준다"""
    pages = c.get("doc_pages") or d.get("doc_pages") or docs.discover_doc_pages(c, q.get("pages") or [], budget=budget) or docs.deep_pages(starts(c, q))
    found = []
    for pg in pages or []:
        try:
            found += docs.scan_docs(jp_ir_qa._text(jp_ir_qa.fetch(pg)), pg)
        except Exception:
            continue
    return row(cid, c, d, q, prof, pages=pages or [], docs_found=found, year=year), pages or []


def live():
    """전 회사를 실제로 스캔해 표를 쓰고, 새로 찾은 자료실을 수집기 상태에 넣는다"""
    cfg = (common.load_yaml("config/jp_ir.yaml") or {}).get("companies") or {}
    st = common.load_state("jp_ir_docs", {"companies": {}})
    q = common.load_state("jp_ir_qa", {"companies": {}})
    prof, year, rows = q.get("profiles") or {}, common.now_kst().year, []
    for cid, c in cfg.items():
        cs = st["companies"].setdefault(cid, {"pages": {}, "seen": []})
        try:
            r, pages = live_row(cid, c, cs, (q.get("companies") or {}).get(cid) or {}, prof.get(cid) or {}, year=year)
        except Exception as exc:
            r, pages = row(cid, c, cs, {}, prof.get(cid) or {}, year=year), []
            r["state"] = f"실패 {type(exc).__name__}"
        rows.append(r)
        if pages and not cs.get("doc_pages"):
            cs["doc_pages"], cs["doc_pages_at"] = pages, common.iso(common.now_kst())
    common.save_state("jp_ir_docs", st)
    write(rows)
    return rows


def write(rows):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def run():
    """run_hourly용 — 주 1회 실제 페이지로 표를 갱신한다"""
    return len(live()), 0


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="실제 페이지를 읽는다(수 분)")
    a = ap.parse_args(argv)
    rows = live() if a.live else table()
    tally = {}
    for r in rows:
        tally[r["state"]] = tally.get(r["state"], 0) + 1
    print(f"[일본 IR 커버리지] {len(rows)}곳 · {tally}")
    for r in rows:
        if r["state"] != "전문·Q&A 있음":
            print(f"{r['id']}: {r['state']} · 최신 {r['latest_period'] or '-'} · 자료실 {r['doc_pages']} · {r['qa_format'] or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
