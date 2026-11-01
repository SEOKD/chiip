"""데이터 2순위 채널 호출 순서 (마스터 지시 2026-11-01, config/data_sources.yaml, ADR-014)

Fiscal.ai 칸이 빈 항목에서 Easyconomics·Zacks·yfinance를 균형 있게 쓴다. 지금까지 덜 쓴 채널이 앞이고, 같으면 회차마다 돌아간다.
Easyconomics는 하루 상한이나 호출 제한 응답이 있으면 그 시간 동안 뒤로 보낸다. yfinance 자료는 Easyconomics MCP로 받으므로 함께 묶인다(config/data_sources.yaml via).
사용: py scripts/fiscal/source_router.py next <항목>        # 이번 회차 순서 출력(차례를 넘긴다)
      py scripts/fiscal/source_router.py used easyconomics [횟수]
      py scripts/fiscal/source_router.py limited easyconomics   # 호출 제한 응답을 받았을 때
      py scripts/fiscal/source_router.py status
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common  # noqa: E402

STATE = "data_sources"


def config():
    return common.load_yaml("config/data_sources.yaml")


def available(src, st, cfg, now):
    """호출 상한·제한 대기에 걸리지 않았으면 True. 상한이 없는 채널은 항상 True"""
    src = (cfg.get("via") or {}).get(src, src)
    lim = (cfg.get("limits") or {}).get(src)
    if not lim:
        return True
    s = (st.get("sources") or {}).get(src) or {}
    if s.get("until") and datetime.fromisoformat(s["until"]) > now:
        return False
    return s.get("day") != now.date().isoformat() or s.get("calls", 0) < lim["daily_cap"]


def order(item, st, cfg, now):
    """이번 회차 순서. 항목을 낼 수 없는 상태의 채널은 뒤로 보낸다"""
    pool = cfg["items"][item]["tier2"]
    n = (st.get("turns") or {}).get(item, 0) % len(pool)
    done = (st.get("served") or {}).get(item) or {}
    seq = sorted(pool[n:] + pool[:n], key=lambda s: done.get(s, 0))   # 정렬은 안정적이라 같은 횟수면 차례를 유지한다
    return [s for s in seq if available(s, st, cfg, now)] + [s for s in seq if not available(s, st, cfg, now)]


def advance(item, now=None):
    now = now or common.now_kst()
    st, cfg = common.load_state(STATE, {}), config()
    seq = order(item, st, cfg, now)
    turns = st.setdefault("turns", {})
    turns[item] = turns.get(item, 0) + 1
    done = st.setdefault("served", {}).setdefault(item, {})
    done[seq[0]] = done.get(seq[0], 0) + 1
    common.save_state(STATE, st)
    return seq


def served(item):
    return dict((common.load_state(STATE, {}).get("served") or {}).get(item) or {})


def save_served(item, tally):
    st = common.load_state(STATE, {})
    st.setdefault("served", {})[item] = tally
    common.save_state(STATE, st)


def used(src, n=1, now=None):
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    s = st.setdefault("sources", {}).setdefault(src, {})
    if s.get("day") != now.date().isoformat():
        s.update({"day": now.date().isoformat(), "calls": 0})
    s["calls"] += n
    common.save_state(STATE, st)
    return s["calls"]


def limited(src, now=None):
    now = now or common.now_kst()
    st, cfg = common.load_state(STATE, {}), config()
    until = now + timedelta(hours=cfg["limits"][src]["cooldown_h"])
    st.setdefault("sources", {}).setdefault(src, {})["until"] = common.iso(until)
    common.save_state(STATE, st)
    return until


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    cfg = config()
    if len(argv) >= 2 and argv[0] == "next":
        it = cfg["items"][argv[1]]
        seq = advance(argv[1])
        print(f"[{it['name']}] 1순위 fiscal → 2순위 " + " → ".join(seq))
        for s in seq:
            print(f"- {s}: {it.get(s)}")
        return 0
    if len(argv) >= 2 and argv[0] == "used":
        print(f"[{argv[1]}] 오늘 {used(argv[1], int(argv[2]) if len(argv) > 2 else 1)}회")
        return 0
    if len(argv) >= 2 and argv[0] == "limited":
        print(f"[{argv[1]}] {limited(argv[1]):%m-%d %H:%M}까지 뒤로 보낸다")
        return 0
    if argv[:1] == ["status"]:
        st, now = common.load_state(STATE, {}), common.now_kst()
        for src in cfg.get("limits") or {}:
            s = (st.get("sources") or {}).get(src) or {}
            print(f"{src}: 오늘 {s.get('calls', 0) if s.get('day') == now.date().isoformat() else 0}회 · 사용 가능 {available(src, st, cfg, now)}")
        for item in cfg["items"]:
            print(f"{item}: {' → '.join(order(item, st, cfg, now))} · 사용 {(st.get('served') or {}).get(item) or {}}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
