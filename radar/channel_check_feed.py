"""Chiip Memory Channel Check — 노션 Informations > Memory Channel Check에 올라오는 PDF를 **모두** 읽고 풀이·해설해 텔레그램으로
(마스터 지시 2026-11-18 "Memory Channel Check 페이지를 읽고 IB Report처럼 텔레그램 피드로 분석해서 제공하라. IB Report에서는 pdf를
선별했다면 Memory Channel Check에는 업로드되는 모든 pdf를 모두 읽고 풀이 및 해설한 후 텔레그램 피드로 제공하라" · 같은 날 "읽되 로컬 참고만").

IB Digest(radar/ib_digest_feed.py)와 다른 점: 고르지 않는다 — 새 PDF 1건 = 해설 1통. 회차당 MAX_SEND통, 남은 것은 다음 회차.
경계: 채널체크는 필드 인텔일 수 있어 다른 기능(Pulse 본문·리포트·Analysis·invest·public)에 내주지 않는다(config/notion_library.yaml blocked_classes).
  해설은 마스터 개인 봇으로만 보내고, 요지·해설 문안은 저장소에 커밋하지 않는다(radar/inbox/channel_check/, git 제외).
  원문 문장·도표를 옮기지 않고 자기 말로 쓴다.
사용: py radar/channel_check_feed.py --status            # 새 채널체크 PDF(올린 순)
      py radar/channel_check_feed.py --send <json 파일>   # {id, summary, claims[3~8], numbers[2~8], korea, weak, next} 1건 → 1통
      py radar/channel_check_feed.py --done <id> [...]     # 읽을 수 없는 자료 등 보내지 않고 표시
      py radar/channel_check_feed.py --pages <id>          # 이미지 PDF(scanned) 페이지를 PNG로 떠서 그림으로 읽는다
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

STATE = "channel_check_feed"
CLS = "채널체크"
MAX_SEND = 3       # 회차당 해설 통수 — 나머지는 다음 회차(모든 PDF를 보낸다)
MSG_MAX = 3800
OUT = common.ROOT / "radar" / "inbox" / "channel_check"   # git 제외


def candidates(rows=None, st=None, today=None):
    import notion_library as NL
    rows = rows if rows is not None else NL.read()
    st = st if st is not None else common.load_state(STATE, {})
    if "baseline" not in st:   # 처음: 지시 전날까지 올라온 자료는 기준선, 그 뒤 올린 것부터 보낸다
        cut = ((today or date.today()) - timedelta(days=1)).isoformat()
        st = {"baseline": sorted(r["id"] for r in rows if r["cls"] == CLS and r["added"] < cut), "done": []}
    seen = set(st["baseline"]) | set(st.get("done") or [])
    out, waiting = [], []
    for r in sorted((r for r in rows if r["cls"] == CLS and r["id"] not in seen), key=lambda r: (r["added"], r["name"])):
        if r["status"] in ("text", "digest"):
            out.append({"id": r["id"], "name": r["name"], "broker": r.get("broker"), "doc_date": r.get("doc_date"), "added": r["added"],
                        "chars": int(r.get("chars") or 0), "text": f"radar/inbox/notion_files/{r['id']}.txt",
                        # 글자 없는 이미지 PDF(11/18 Nomura — 추출 70자): 페이지를 그림으로 떠서 읽는다 → --pages <id>
                        "scanned": int(r.get("chars") or 0) < 2000})
        else:
            waiting.append({"id": r["id"], "name": r["name"], "status": r["status"]})   # 아직 텍스트를 못 뽑음 — 수집기가 다시 받는다
    return out, waiting, st


def status(now=None):
    """Pulse 관문 — 새 채널체크 PDF가 있으면 due"""
    try:
        cands, waiting, st = candidates()
    except Exception as e:
        return {"due": False, "error": type(e).__name__}
    if not common.load_state(STATE, {}).get("baseline"):
        common.save_state(STATE, st)
    return {"due": bool(cands), "n": len(cands), "max_send": MAX_SEND, "todo": cands[:MAX_SEND], "waiting_text": waiting}


def message(p, rows=None):
    import notion_library as NL
    rows = {r["id"]: r for r in (rows if rows is not None else NL.read())}
    r = rows.get(p["id"]) or {}
    title = re.sub(r"\.pdf$", "", str(r.get("name") or p["id"]), flags=re.I).replace("_", " ")
    meta = " · ".join(x for x in (r.get("broker") if r.get("broker") not in (None, "", "미확인") else "", r.get("doc_date") or "") if x)
    L = ["[Chiip Memory Channel Check]", title[:110] + (f" ({meta})" if meta else ""), "",
         f"■ 풀이: {p['summary']}", "", "■ 핵심 내용", ""] + [f"• {x}" for x in p["claims"]]
    L += ["", "■ 근거 숫자", ""] + [f"• {x}" for x in p["numbers"]]
    L += ["", "■ 한국 메모리에 주는 뜻", p["korea"], "", "■ 약한 고리", p["weak"], "", "■ 다음 확인", p["next"]]
    return "\n".join(L)


def check(p, rows=None):
    bad = []
    miss = [k for k in ("id", "summary", "korea", "weak", "next") if not str(p.get(k) or "").strip()]
    if miss:
        bad.append(", ".join(miss) + " 없음")
    if not 3 <= len(p.get("claims") or []) <= 8:
        bad.append("핵심 내용 3~8개")
    if not 2 <= len(p.get("numbers") or []) <= 8:
        bad.append("근거 숫자 2~8개")
    if any(len(x) > 260 for x in (p.get("claims") or []) + (p.get("numbers") or [])):
        bad.append("항목은 260자 안")
    if re.search(r"(사라[.!\s]|사라$|팔아라|매수하라|매도하라|비중 확대|비중 축소)", json.dumps(p, ensure_ascii=False)):
        bad.append("매매 지시 표현")
    if not bad and len(message(p, rows)) > MSG_MAX:
        bad.append(f"해설 {len(message(p, rows))}자 — 한 통 {MSG_MAX}자 안으로")
    return bad


def done(ids):
    st = common.load_state(STATE, {})
    if "baseline" not in st:
        _, _, st = candidates(st={})
    st["done"] = sorted(set(st.get("done") or []) | set(ids))
    common.save_state(STATE, st)


def pages(bid, dpi=110, max_pages=15):
    """이미지 PDF를 페이지 PNG로(radar/inbox/channel_check/<id>/pN.png, git 제외) — 노션 API 서명 주소로 받는다"""
    import urllib.request
    import notion_library as NL
    import pymupdf
    b = NL.api_get(f"/blocks/{bid}", common.load_env()["NOTION_TOKEN"])
    f = b[b["type"]].get("file") or b[b["type"]].get("external") or {}
    with urllib.request.urlopen(f["url"], timeout=60) as r:
        doc = pymupdf.open(stream=r.read(), filetype="pdf")
    d = OUT / bid
    d.mkdir(parents=True, exist_ok=True)
    out = []
    for i in range(min(doc.page_count, max_pages)):
        p = d / f"p{i + 1}.png"
        doc[i].get_pixmap(dpi=dpi).save(str(p))
        out.append(str(p))
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--pages"]:
        print("\n".join(pages(argv[1])))
        return 0
    if argv[:1] == ["--send"]:
        p = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        p = p[0] if isinstance(p, list) else p
        bad = check(p)
        if bad:
            raise SystemExit("Channel Check 관문 — " + " · ".join(bad))
        import notify
        text = message(p)
        ok = notify.send(text, "P1")
        if ok:
            OUT.mkdir(parents=True, exist_ok=True)
            (OUT / f"{p['id']}.txt").write_text(text, encoding="utf-8")
            done([p["id"]])
        print("[Channel Check] 발송" if ok else "[Channel Check] 발송 실패")
        return 0
    if argv[:1] == ["--done"]:
        done(argv[1:])
        print(f"[Channel Check] {len(argv) - 1}건 표시")
        return 0
    print(json.dumps(status(), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
