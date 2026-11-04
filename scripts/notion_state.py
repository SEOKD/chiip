"""노션 감시 상태 (마스터 지시 2026-10-28 "노션에 올리는 즉시 파악해 결과물을 텔레그램으로")

마스터 노션 Insights·Informations·Stocks 아래 페이지마다 '어느 수정본까지 처리했나'를 radar/state/notion_watch.json에 둔다.
결정론 감시기(radar/notion_watch.py, NOTION_TOKEN 필요)와 예약 작업(chiip-notion-watch, 노션 커넥터)이 같은 상태를 쓴다.
baseline: 감시를 켤 때 이미 있던 페이지 — 다음에 수정될 때만 처리한다.
사용: py scripts/notion_state.py decide <role> <page_id> <title> [last_edited_iso]   → NEW | CHANGED | SKIP
      py scripts/notion_state.py mark <page_id> <last_edited_iso|-> [report_path]
      py scripts/notion_state.py baseline <role> <page_id> <title> [last_edited_iso]
      py scripts/notion_state.py list
"""
import json
import sys
from datetime import datetime
from pathlib import Path

STATE = Path(__file__).resolve().parents[1] / "radar" / "state" / "notion_watch.json"
SKIP_PREFIX = ("치입 검토",)   # 치입이 만든 하위 페이지는 처리 대상이 아니다


def _key(pid):
    return pid.replace("-", "").lower()


def load():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"pages": {}}


def save(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def decide(role, pid, title, edited=None, st=None):
    """NEW(처음 보는 페이지) | CHANGED(처리 뒤 수정됨) | SKIP. 상태에 제목·역할·최근 수정 시각을 기록한다(처리 표시는 mark)"""
    if title.strip().startswith(SKIP_PREFIX):
        return "SKIP"
    own = st is None
    st = st or load()
    k = _key(pid)
    r = st["pages"].get(k)
    if r is None:
        st["pages"][k] = {"role": role, "title": title, "last_edited": edited, "processed_edit": None, "baseline": False}
        out = "NEW"
    else:
        r.update({"title": title, "role": role})
        if edited:
            r["last_edited"] = edited
        if r.get("baseline") and not r.get("processed_edit"):
            r["processed_edit"] = edited      # 기준선 페이지는 처음 본 수정 시각을 '처리됨'으로 잡는다
            out = "SKIP"
        elif edited and r.get("processed_edit") and _ts(edited) > _ts(r["processed_edit"]):
            out = "CHANGED"
        elif not r.get("processed_edit") and not r.get("baseline"):
            out = "NEW"                        # 이전에 감지됐지만 아직 처리 안 됨
        else:
            out = "SKIP"
    if own:
        save(st)
    return out


def mark(pid, edited, report="", st=None):
    own = st is None
    st = st or load()
    r = st["pages"].setdefault(_key(pid), {"role": "", "title": ""})
    r["processed_edit"] = None if edited in (None, "-") else edited
    if r["processed_edit"] is None:
        r["processed_edit"] = r.get("last_edited") or datetime.now().astimezone().isoformat()
    r["report"] = report
    r["processed_at"] = datetime.now().astimezone().isoformat()
    r["baseline"] = r.get("baseline", False)
    if own:
        save(st)


def _lines(text):
    """비교 단위 = 줄(공백 정리, 2자 미만·구분선 제외) → 짧은 해시. 상태에는 해시만 둔다(본문을 남기지 않는다)"""
    import hashlib
    out = {}
    for ln in str(text).splitlines():
        s = " ".join(ln.split()).strip("-*#> ")
        if len(s) >= 2:
            out.setdefault(hashlib.sha1(s.encode("utf-8")).hexdigest()[:12], ln)
    return out


def fresh(pid, text, st=None):
    """Informations 새 정보만(마스터 지시 2026-11-04 "새 정보가 들어오면 새 정보만 — 이전에 올린 정보를 다시 다룰 필요가 없다").
    → (새 줄 목록, 이전 기록 있음 여부). 이전 기록이 없으면(처음 보는 페이지·기능 도입 전 페이지) 전부 새 줄로 돌려준다"""
    st = st or load()
    seen = set((st["pages"].get(_key(pid)) or {}).get("seen_lines") or [])
    return [ln for h, ln in _lines(text).items() if h not in seen], bool(seen)


def remember(pid, text, st=None):
    """처리한 본문의 줄 해시를 기억한다(다음 수정 때 새 줄만 고르게)"""
    own = st is None
    st = st or load()
    r = st["pages"].setdefault(_key(pid), {"role": "", "title": ""})
    r["seen_lines"] = sorted(set(r.get("seen_lines") or []) | set(_lines(text)))
    if own:
        save(st)


def baseline(role, pid, title, edited=None, st=None):
    own = st is None
    st = st or load()
    st["pages"][_key(pid)] = {"role": role, "title": title, "last_edited": edited, "processed_edit": edited, "baseline": True}
    if own:
        save(st)


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    cmd = argv[0]
    if cmd == "decide":
        print(decide(argv[1], argv[2], argv[3], argv[4] if len(argv) > 4 else None))
    elif cmd == "mark":
        mark(argv[1], argv[2] if len(argv) > 2 else None, argv[3] if len(argv) > 3 else "")
        print("marked")
    elif cmd == "baseline":
        baseline(argv[1], argv[2], argv[3], argv[4] if len(argv) > 4 else None)
        print("baseline")
    elif cmd == "fresh":   # fresh <page_id> <본문 파일> → 새 줄만 출력(없으면 'NONE')
        new, had = fresh(argv[1], Path(argv[2]).read_text(encoding="utf-8"))
        print("\n".join(new) if new else "NONE")
        if not had:
            print("(이전 기록 없음 — 직전 상세 보고서와 겹치는 내용은 빼고 다룬다)", file=sys.stderr)
    elif cmd == "remember":   # remember <page_id> <본문 파일>
        remember(argv[1], Path(argv[2]).read_text(encoding="utf-8"))
        print("remembered")
    elif cmd == "list":
        for k, v in load()["pages"].items():
            print(k, v.get("role"), v.get("title"), "처리:", v.get("processed_edit"), "기준선" if v.get("baseline") else "")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
