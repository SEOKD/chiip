"""예약 작업 누락 재실행 판정 (마스터 지시 2026-11-04 "각 기능이 주기대로 실행 실패하면 넘어간 태스크를 반드시 재시행하는 구조")

앱 예약(scheduled-tasks)은 PC가 꺼져 있거나 잠들었거나 실행이 실패하면 그 회차를 건너뛴다. 감시 예약 chiip-catchup이
list_scheduled_tasks·list_task_runs 결과를 JSON으로 저장하면, 이 스크립트가 크론식으로 '있어야 할 회차'를 계산해 실행 기록과 맞춘다.
판정(작업마다):
  - 마지막 예정 회차 = 지금 − 유예(grace)보다 앞선 가장 최근 크론 시각(KST).
  - 그 회차 이후 시작한 실행이 하나라도 있고 그것이 실패가 아니면 정상. 진행 중(running)이면 기다린다.
  - 없거나 실패뿐이면 '누락' → 한 번만 재실행. 고빈도 작업(펄스 10분 등)도 놓친 회차를 하나하나 메우지 않는다 — 다음 실행이 앞 회차 일을 이어받는다.
  - 같은 회차를 두 번 재실행하지 않는다(radar/state/catchup.json에 회차 기록).
  - 재실행 대상에서 빼는 작업: 꺼진 작업, 1회성(월·일이 고정된) 작업, 자기 자신. 24시간보다 오래된 누락은 stale로 알리기만 한다.
  - 실행 기록이 한 번도 없는 작업은 감시기가 처음 본 시각(first_seen) 이전 회차를 누락으로 치지 않는다(새로 만든 작업).
사용: py scripts/ops/catchup.py <상태 JSON>   — {"now": ISO, "tasks": [list_scheduled_tasks 행 + "runs": [list_task_runs 행]]}
      → {"rerun": [{"taskId", "slot", "why"}], "ok": n, "waiting": [...]}   모델은 rerun의 taskId마다 run_scheduled_task를 부르고 --mark로 기록한다.
      py scripts/ops/catchup.py --mark <taskId> <slot ISO>
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "radar" / "state" / "catchup.json"
KST = timezone(timedelta(hours=9))
SELF = "chiip-catchup"
LOOKBACK_H = 24 * 8   # 주 1회 작업까지 회차를 찾는다
MAX_AGE_H = 24       # 이보다 오래된 누락은 재실행하지 않고 알리기만 한다(지난 회차가 오늘 판단을 낡게 만들지 않게)
MIN_GRACE_MIN = 25


def _field(spec, lo, hi):
    out = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, s = part.split("/")
            step = int(s)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = map(int, part.split("-"))
        else:
            a = b = int(part)
        out.update(range(a, b + 1, step))
    return out


def parse(cron):
    m, h, dom, mon, dow = cron.split()
    dows = {d % 7 for d in _field(dow, 0, 7)}
    return {"m": _field(m, 0, 59), "h": _field(h, 0, 23), "dom": _field(dom, 1, 31), "mon": _field(mon, 1, 12), "dow": dows,
            "dom_any": dom == "*", "dow_any": dow == "*", "oneoff": dom != "*" and mon != "*" and "," not in dom + mon and "-" not in dom + mon and "/" not in dom + mon}


def matches(c, t):
    if t.minute not in c["m"] or t.hour not in c["h"] or t.month not in c["mon"]:
        return False
    d_ok, w_ok = t.day in c["dom"], (t.isoweekday() % 7) in c["dow"]
    if c["dom_any"] or c["dow_any"]:
        return d_ok and w_ok
    return d_ok or w_ok   # 크론 관례: 일·요일이 둘 다 지정되면 어느 하나


def last_slot(cron, before, lookback_h=LOOKBACK_H):
    """before(KST) 이전 가장 최근 회차"""
    c = parse(cron)
    t = before.astimezone(KST).replace(second=0, microsecond=0)
    for _ in range(lookback_h * 60):
        if matches(c, t):
            return t
        t -= timedelta(minutes=1)
    return None


def _dt(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


def judge(doc, state=None):
    state = state if state is not None else (json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {})
    now = _dt(doc["now"]) if doc.get("now") else datetime.now(KST)
    out = {"rerun": [], "ok": 0, "waiting": [], "skipped": [], "stale": []}
    seen = state.setdefault("_first_seen", {})
    for t in doc.get("tasks") or []:
        tid, cron = t.get("taskId"), t.get("cronExpression")
        if not cron or tid == SELF or not t.get("enabled", True):
            out["skipped"].append(tid)
            continue
        if parse(cron)["oneoff"]:
            out["skipped"].append(tid)
            continue
        grace = timedelta(minutes=max(MIN_GRACE_MIN, (t.get("jitterSeconds") or 0) / 60 + 15))
        slot = last_slot(cron, now - grace)
        if not slot:
            out["skipped"].append(tid)
            continue
        first = seen.setdefault(tid, now.isoformat())
        if not t.get("runs") and not t.get("lastRunAt") and slot < _dt(first):
            out["skipped"].append(tid)
            continue
        allr = t.get("runs")
        if allr is None and t.get("lastRunAt"):   # 실행 기록을 받지 않았으면 lastRunAt만으로 본다(상태는 성공으로 가정)
            allr = [{"started_at": t["lastRunAt"], "status": "unknown"}]
        runs = [r for r in allr or [] if r.get("started_at") and _dt(r["started_at"]) >= slot - timedelta(minutes=1)]
        if any(r.get("status") in ("running", "starting", "pending") for r in runs):
            out["waiting"].append(tid)
            continue
        if any(r.get("status") not in ("failed", "error", "cancelled", "stopped") for r in runs):
            out["ok"] += 1
            continue
        key = slot.isoformat()
        if (state.get(tid) or {}).get("slot") == key:
            out["skipped"].append(tid)   # 이 회차는 이미 재실행했다
            continue
        if now - slot > timedelta(hours=MAX_AGE_H):
            out["stale"].append({"taskId": tid, "slot": key})
            continue
        out["rerun"].append({"taskId": tid, "title": t.get("title") or tid, "slot": key, "why": "실패" if runs else "실행 기록 없음"})
    return out


def mark(tid, slot):
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    st[tid] = {"slot": slot, "at": datetime.now(KST).isoformat()}
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) == 3 and argv[0] == "--mark":
        mark(argv[1], argv[2])
        print("marked")
        return 0
    if len(argv) != 1:
        print(__doc__)
        return 1
    st = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    print(json.dumps(judge(json.loads(Path(argv[0]).read_text(encoding="utf-8")), st), ensure_ascii=False, indent=1))
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
