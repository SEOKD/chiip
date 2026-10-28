"""인사이트 검토 상태 (스킬 insight-review) — 노션 Insights 하위 페이지마다 '어느 수정본까지 검토했나'

노션 페이지에는 속성 칸이 없어 검토 기록을 radar/state/insight_reviews.json에 둔다.
치입이 검토 하위 페이지를 만들면 부모의 수정 시각도 바뀔 수 있으므로, 검토를 마친 뒤 페이지를 다시 읽어
그때의 수정 시각을 mark한다(자기 기록 때문에 재검토되지 않게).
사용: py scripts/insight_state.py check <page_id> <last_edited_iso>   → DUE 또는 SKIP 출력
      py scripts/insight_state.py mark <page_id> <last_edited_iso> <review_page_url>
      py scripts/insight_state.py list
"""
import json
import sys
from datetime import datetime
from pathlib import Path

STATE = Path(__file__).resolve().parents[1] / "radar" / "state" / "insight_reviews.json"


def _load():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def _ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def check(pid, edited):
    r = _load().get(pid.replace("-", ""))
    return "DUE" if not r or _ts(edited) > _ts(r["reviewed_edit"]) else "SKIP"


def mark(pid, edited, url):
    st = _load()
    st[pid.replace("-", "")] = {"reviewed_edit": edited, "review_page": url, "marked_at": datetime.now().astimezone().isoformat()}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    if argv[0] == "check":
        print(check(argv[1], argv[2]))
    elif argv[0] == "mark":
        mark(argv[1], argv[2], argv[3] if len(argv) > 3 else "")
        print("marked")
    elif argv[0] == "list":
        for k, v in _load().items():
            print(k, v["reviewed_edit"], v.get("review_page", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
