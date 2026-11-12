"""Chiip IB Digest — 노션 IB Report에 새 PDF가 올라오면 가치가 높은 몇 건을 골라 요약을 텔레그램으로 (마스터 지시 2026-11-08
"IB Report에 새로운 PDF 파일이 올라오면 스스로 판단하기에 밸류가 높은 리포트 몇 개를 직접 선정하고 이 리포트들을 요약해 텔레그램 피드로 전달")

결정론: 새 IB PDF(knowledge/notion/library.csv, radar/notion_library.py가 30분마다 색인·텍스트 추출)를 찾고 1차 점수(prescore)를 매긴다. 고르기·요약은 모델(Pulse 2-6).
  prescore = 감시 종목 주 대상 3 / 업종·테마 연결 2 + 문서 유형(개시·등급 변경·목표가 변경·입문서·심층 2, 실적 첫인상 1) + 분량(4만 자 이상 1) + 증권사 확인 0.5
+ 2026-11-12 마스터 지시 "IB Report에 새로 올라오는 pdf 중에 하나 골라 풀이할 때 해석본 한 개만 보내라. 하나의 리포트를 갖고 여러 차례
  보내던데 그러지 말라 … 대신 한 번 해석할 때 상세하게 풀이하라": 회차당 1건만, 같은 리포트는 한 번만(같은 PDF를 두 번 올려 id가 둘이어도
  파일 이름 열쇠로 막는다 — 11/12 Top of Mind 중복 발송), 해석은 결론·핵심 주장·근거 숫자·논리·시장 기대와 차이·약한 고리·다음 확인으로 상세하게.
발송 양식은 이 스크립트가 고정한다(--send). 요약은 자기 말로만(원문 문장·도표 복제 금지 — notion_library --digest가 겹침을 거절), 마스터 개인 봇만.
사용: py radar/ib_digest_feed.py --status             # 새 IB PDF 후보(prescore 순)
      py radar/ib_digest_feed.py --send <json 파일>    # [{id, why, conclusion, claims[3~6], numbers[2~6], logic, gap, weak, next}] 1건 → 텔레그램 1통
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
MAX_PICK = 1      # 회차당 해석본 1건(2026-11-12 마스터 지시)
MSG_MAX = 3800    # 텔레그램 한 통(4,096자) 안


def report_key(name):
    """같은 리포트 판별 열쇠 — 확장자·기호·공백을 걷어낸 파일 이름(같은 PDF를 두 번 올리면 id만 다르다)"""
    return re.sub(r"[\W_]+", "", re.sub(r"\.pdf$", "", str(name or ""), flags=re.I).lower())


def candidates(rows=None, st=None, cfg=None):
    import notion_library as NL
    rows = rows if rows is not None else NL.read()
    cfg = cfg or NL.config()
    st = st if st is not None else common.load_state(STATE, {})
    if "baseline" not in st:   # 처음 실행: 지금까지 쌓인 자료는 기준선(새 PDF만 보낸다)
        return [], {"baseline": sorted(r["id"] for r in rows if r["cls"] == "IB 리포트"), "done": []}
    seen = set(st["baseline"]) | set(st.get("done") or [])
    sent_keys = set(st.get("sent_keys") or [])
    out, keys = [], set()
    themes = None
    for r in rows:
        if r["cls"] != "IB 리포트" or r["id"] in seen or r["status"] not in ("text", "digest"):
            continue
        k = report_key(r["name"])
        if k in sent_keys or k in keys:   # 이미 보낸 리포트·이번 목록 안의 중복 사본
            continue
        keys.add(k)
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
    p = picks[0]
    r = rows.get(p["id"]) or {}
    title = re.sub(r"\.pdf$", "", str(r.get("name") or p["id"])).replace("_", " ")
    meta = " · ".join(x for x in (r.get("broker") if r.get("broker") not in (None, "", "미확인") else "", r.get("doc_date") or "") if x)
    L = ["[Chiip IB Digest]", f"{title[:110]}" + (f" ({meta})" if meta else ""), "",
         f"결론: {p['conclusion']}", f"왜 골랐나: {p['why']}", "", "핵심 주장"]
    L += [f"• {x}" for x in p["claims"]]
    L += ["", "근거 숫자"] + [f"• {x}" for x in p["numbers"]]
    L += ["", f"논리: {p['logic']}", "", f"시장 기대·Chiip 판단과의 차이: {p['gap']}", "", f"약한 고리: {p['weak']}", "", f"다음 확인: {p['next']}", ""]
    L.append("IB 원문 요지를 Chiip 말로 줄인 것 — 전망치는 시장 기대의 증거이고 투자 권유가 아님. 외부 공유 금지.")
    return "\n".join(L)


def check(picks, rows=None):
    bad = []
    if len(picks) != MAX_PICK:
        bad.append(f"고른 리포트 {len(picks)}건 — 회차당 {MAX_PICK}건만(2026-11-12 마스터 지시)")
    for p in picks:
        miss = [k for k in ("why", "conclusion", "logic", "gap", "weak", "next") if not str(p.get(k) or "").strip()]
        if miss:
            bad.append(f"{p.get('id')}: {', '.join(miss)} 없음")
        if not 3 <= len(p.get("claims") or []) <= 6:
            bad.append(f"{p.get('id')}: 핵심 주장 3~6개")
        if not 2 <= len(p.get("numbers") or []) <= 6:
            bad.append(f"{p.get('id')}: 근거 숫자 2~6개")
        if any(len(x) > 260 for x in (p.get("claims") or []) + (p.get("numbers") or [])):
            bad.append(f"{p.get('id')}: 항목은 260자 안")
        if re.search(r"(사라|팔아라|매수하라|매도하라|비중 확대|비중 축소)", json.dumps(p, ensure_ascii=False)):
            bad.append(f"{p.get('id')}: 매매 지시 표현")
    if not bad:
        n = len(message(picks, rows))
        if n > MSG_MAX:
            bad.append(f"해석본 {n}자 — 한 통 {MSG_MAX}자 안으로")
    return bad


def done(ids, sent=False, rows=None):
    """본 자료 표시. 보낸 리포트는 이름 열쇠도 남겨 같은 PDF의 다른 사본까지 막는다"""
    st = common.load_state(STATE, {})
    ids = set(ids)
    if sent:
        import notion_library as NL
        rows = rows if rows is not None else NL.read()
        names = {r["id"]: r["name"] for r in rows}
        keys = {report_key(names.get(i, "")) for i in ids} - {""}
        st["sent_keys"] = sorted(set(st.get("sent_keys") or []) | keys)
        ids |= {r["id"] for r in rows if report_key(r["name"]) in keys}
    st["done"] = sorted(set(st.get("done") or []) | ids)
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
            done([p["id"] for p in picks], sent=True)
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
