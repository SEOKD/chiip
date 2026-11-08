"""Chiip IB Digest — 노션 IB Report에 새 PDF가 올라오면 가치가 높은 몇 건을 골라 요약을 텔레그램으로 (마스터 지시 2026-11-08
"IB Report에 새로운 PDF 파일이 올라오면 스스로 판단하기에 밸류가 높은 리포트 몇 개를 직접 선정하고 이 리포트들을 요약해 텔레그램 피드로 전달")

결정론: 새 IB PDF(knowledge/notion/library.csv, radar/notion_library.py가 30분마다 색인·텍스트 추출)를 찾고 1차 점수(prescore)를 매긴다. 고르기·요약은 모델(Pulse 2-6).
  prescore = 감시 종목 주 대상 3 / 업종·테마 연결 2 + 문서 유형(개시·등급 변경·목표가 변경·입문서·심층 2, 실적 첫인상 1) + 분량(4만 자 이상 1) + 증권사 확인 0.5
발송 양식은 이 스크립트가 고정한다(--send). 요약은 자기 말로만(원문 문장·도표 복제 금지 — notion_library --digest가 겹침을 거절), 마스터 개인 봇만.
사용: py radar/ib_digest_feed.py --status             # 새 IB PDF 후보(prescore 순)
      py radar/ib_digest_feed.py --send <json 파일>    # [{id, why, points[2~4], chiip}] → 텔레그램 1통
      py radar/ib_digest_feed.py --done <id> [<id> ...]   # 본 자료 표시(보낸 것·안 고른 것 모두)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

STATE = "ib_digest_feed"
TYPE_HI = re.compile(r"Initiat|Upgrade|Downgrade|Raise|Cut|Primer|Deep ?Dive|Black ?Book|Outlook|Model|Forecast|개시|상향|하향|입문", re.I)
TYPE_MID = re.compile(r"First ?Take|Earnings|Review|Q[1-4]|[1-4]Q", re.I)
MAX_PICK = 3


def candidates(rows=None, st=None, cfg=None):
    import notion_library as NL
    rows = rows if rows is not None else NL.read()
    cfg = cfg or NL.config()
    st = st if st is not None else common.load_state(STATE, {})
    if "baseline" not in st:   # 처음 실행: 지금까지 쌓인 자료는 기준선(새 PDF만 보낸다)
        return [], {"baseline": sorted(r["id"] for r in rows if r["cls"] == "IB 리포트"), "done": []}
    seen = set(st["baseline"]) | set(st.get("done") or [])
    out = []
    themes = None
    for r in rows:
        if r["cls"] != "IB 리포트" or r["id"] in seen or r["status"] not in ("text", "digest"):
            continue
        name = r["name"].replace("_", " ")
        s, why = 0.0, []
        if r["entities"]:
            s += 3
            why.append("감시 종목 주 대상")
        else:
            if themes is None:
                themes = cfg.get("themes") or []
            if any(any(re.search(m, name, re.I) for m in t["match"]) for t in themes):
                s += 2
                why.append("업종·테마(세부 산업 연결)")
        if TYPE_HI.search(name):
            s += 2
            why.append("개시·등급/목표가 변경·입문서·전망")
        elif TYPE_MID.search(name):
            s += 1
            why.append("실적 리뷰")
        if int(r.get("chars") or 0) >= 40000:
            s += 1
            why.append("심층 분량")
        if r.get("broker") and r["broker"] != "미확인":
            s += 0.5
        out.append({"id": r["id"], "name": r["name"], "broker": r.get("broker"), "doc_date": r.get("doc_date"), "entities": r["entities"],
                    "chars": int(r.get("chars") or 0), "prescore": s, "why": why, "text": f"radar/inbox/notion_files/{r['id']}.txt", "digest": r["status"] == "digest"})
    return sorted(out, key=lambda x: -x["prescore"]), st


def status(now=None):
    """Pulse 관문 — 새 IB PDF가 있으면 due"""
    try:
        cands, st = candidates()
    except Exception as e:
        return {"due": False, "error": type(e).__name__}
    if "done" in st and "baseline" in st and not common.load_state(STATE, {}).get("baseline"):
        common.save_state(STATE, st)   # 첫 기준선 저장
    return {"due": bool(cands), "n": len(cands), "top": [{k: c[k] for k in ("id", "name", "broker", "doc_date", "entities", "prescore", "why", "text")} for c in cands[:8]],
            "max_pick": MAX_PICK}


def message(picks, rows=None):
    import notion_library as NL
    rows = {r["id"]: r for r in (rows if rows is not None else NL.read())}
    L = ["[Chiip IB Digest]", f"새 IB 리포트 중 {len(picks)}건 — Chiip이 고른 것", ""]
    for i, p in enumerate(picks, 1):
        r = rows.get(p["id"]) or {}
        title = re.sub(r"\.pdf$", "", str(r.get("name") or p["id"])).replace("_", " ")
        meta = " · ".join(x for x in (r.get("broker") if r.get("broker") not in (None, "", "미확인") else "", r.get("doc_date") or "") if x)
        L.append(f"{i}. {title[:90]}" + (f" ({meta})" if meta else ""))
        L.append(f"왜 골랐나: {p['why']}")
        L += [f"• {x}" for x in p["points"]]
        if p.get("chiip"):
            L.append(f"Chiip: {p['chiip']}")
        L.append("")
    L.append("IB 원문 요지를 Chiip 말로 줄인 것 — 전망치는 시장 기대의 증거이고 투자 권유가 아님. 외부 공유 금지.")
    return "\n".join(L)


def check(picks):
    bad = []
    if not 1 <= len(picks) <= MAX_PICK:
        bad.append(f"고른 리포트 {len(picks)}건 — 1~{MAX_PICK}건")
    for p in picks:
        if not p.get("why") or not 2 <= len(p.get("points") or []) <= 4:
            bad.append(f"{p.get('id')}: why와 요점 2~4개 필요")
        if any(len(x) > 160 for x in p.get("points") or []):
            bad.append(f"{p.get('id')}: 요점은 160자 안")
        if re.search(r"(사라|팔아라|매수하라|매도하라|비중 확대|비중 축소)", json.dumps(p, ensure_ascii=False)):
            bad.append(f"{p.get('id')}: 매매 지시 표현")
    return bad


def done(ids):
    st = common.load_state(STATE, {})
    st["done"] = sorted(set(st.get("done") or []) | set(ids))
    common.save_state(STATE, st)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--send"]:
        picks = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        bad = check(picks)
        if bad:
            raise SystemExit("IB Digest 관문 — " + " · ".join(bad))
        import notify
        ok = notify.send(message(picks), "P1")
        if ok:
            done([p["id"] for p in picks])
        print("[IB Digest] 발송" if ok else "[IB Digest] 발송 실패")
        return 0
    if argv[:1] == ["--done"]:
        done(argv[1:])
        print(f"[IB Digest] {len(argv) - 1}건 표시")
        return 0
    print(json.dumps(status(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
