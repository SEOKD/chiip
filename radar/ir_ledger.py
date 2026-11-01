"""IR 전문·Q&A 처리 장부 (마스터 지시 2026-11-01 "왜 이를 업데이트한 실적 분석 피드를 안 내는가 … 구조를 다시 점검하고 보완을 해 체계적으로 구축하라")

당기 어닝콜 전문·스크립트·Q&A는 분석하거나 제외 사유를 적기 전까지 끝난 것이 아니다. Pulse에 실려 갔다는 것만으로는 처리됐다고 보지 않는다.
처리 기록이 없으면 RETRY_H마다 Pulse에 다시 싣고, OVERDUE_H가 지나면 Proviser가 본다.
사용: py radar/ir_ledger.py --due                     # 대기 목록
      py radar/ir_ledger.py --done <주소> "<분석 파일 또는 제외 사유>"
      py radar/ir_ledger.py --overdue                 # 기한 지난 건 — Proviser
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

STATE = "ir_ledger"
CLASS = "IR 질의응답"
RETRY_H = 3       # 처리 기록 없이 이만큼 지나면 다시 싣는다
OVERDUE_H = 24    # 이만큼 지나도 처리 기록이 없으면 Proviser 점검 대상
MAX_DUE = 6       # 한 회차에 다시 싣는 수


def load():
    st = common.load_state(STATE, {"docs": {}})
    st.setdefault("docs", {})
    return st


def _name(item):
    """같은 파일이 두 주소에 걸리는 회사가 있다(도쿄일렉트론 /ir/irta…·/ir/library/report/…) — 회사와 파일 이름으로 묶는다"""
    return (tuple(item.get("entities_matched") or []), str(item.get("url", "")).split("?")[0].rsplit("/", 1)[-1])


def track(sources, now=None, st=None):
    """이번 회차에 나온 전문·Q&A를 장부에 올린다. 이미 있으면 그대로 둔다"""
    now = now or common.now_kst()
    own = st is None
    st = st if st is not None else load()
    added = 0
    names = {_name(d["item"]) for d in st["docs"].values()}
    for s in sources:
        if s.get("source_class") == CLASS and s.get("url") and s["url"] not in st["docs"] and _name(s) not in names:
            names.add(_name(s))
            st["docs"][s["url"]] = {"item": s, "added": common.iso(now), "offered": None, "tries": 0, "done": None, "note": ""}
            added += 1
    if own and added:
        common.save_state(STATE, st)
    return added


def due(now=None, st=None):
    """처리 기록이 없고 다시 실을 때가 된 건 — 오래 기다린 것부터"""
    now = now or common.now_kst()
    st = st if st is not None else load()
    cut = now - timedelta(hours=RETRY_H)
    rows = [d for d in st["docs"].values() if not d["done"] and (not d["offered"] or datetime.fromisoformat(d["offered"]) <= cut)]
    return sorted(rows, key=lambda d: d["added"])[:MAX_DUE]


def offered(urls, now=None, st=None):
    now = now or common.now_kst()
    own = st is None
    st = st if st is not None else load()
    for u in urls:
        d = st["docs"].get(u)
        if d and not d["done"]:
            d["offered"], d["tries"] = common.iso(now), d["tries"] + 1
    if own:
        common.save_state(STATE, st)


def done(url, note, now=None, st=None):
    now = now or common.now_kst()
    own = st is None
    st = st if st is not None else load()
    if url not in st["docs"]:
        raise SystemExit("장부에 없는 주소")
    if not note.strip():
        raise SystemExit("분석 파일이나 제외 사유를 적는다")
    st["docs"][url].update({"done": common.iso(now), "note": note})
    if own:
        common.save_state(STATE, st)


def overdue(now=None, st=None):
    now = now or common.now_kst()
    st = st if st is not None else load()
    cut = common.iso(now - timedelta(hours=OVERDUE_H))
    return [d for d in st["docs"].values() if not d["done"] and d["added"] <= cut]


def show(rows):
    return "\n".join(f"{d['added'][:16]} · 시도 {d['tries']} · {d['item'].get('title', '')[:70]} · {d['item'].get('url')}" for d in rows)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--due", action="store_true")
    ap.add_argument("--done", nargs=2, metavar=("URL", "NOTE"))
    ap.add_argument("--overdue", action="store_true")
    a = ap.parse_args(argv)
    if a.done:
        done(*a.done)
        print("[IR 장부] 처리 기록")
    elif a.overdue:
        print(show(overdue()) or "기한 지난 건 없음")
    else:
        print(show([d for d in load()["docs"].values() if not d["done"]]) or "대기 없음")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
