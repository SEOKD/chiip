"""TradingView MCP 하루 호출 예산 훅 (2026-11-19 마스터 지시 "일일 한도가 얼마인지 분석하고 이에 맞춰 일일 주기를 조정하라")

분석(세션 기록 2026-10-30~11-19): 11-14·15·16 KST는 하루 149~194건이 막히지 않았는데, 11-17은 90건째(직전 24시간 97건)에
'daily usage limit + 10-minute cooldown'이 걸렸고 그 뒤 이틀 넘게 냉각이 되풀이됐다(냉각 중에도 회차들이 계속 불러 하루 155건이 막힘).
→ 한도는 고정 일일 건수로 보이지 않는다(며칠 누적 또는 사용 패턴 기반으로 추정 — TradingView가 수치를 공개하지 않아 미확인).
   보수적으로 관측된 가장 낮은 차단점(90)보다 아래인 하루 예산을 코드로 지킨다.
pre  : 오늘(KST) 사용 수가 예산 이상이거나, 한도·냉각 오류 뒤 막힘 시각 전이면 호출 거부(deny). 06:00~07:00 KST 전에는 TradingView 동기화 몫(reserve)을 남긴다.
post : 응답에 TOOL_QUOTA_EXCEEDED가 있으면 막힘 시각 설정 — 냉각이면 11분, 'daily usage limit'이면 다음 날 06:00 KST까지(냉각 중 재시도가 한도를 늘리지 않게).
설정 config/tv_budget.yaml, 상태 radar/state/tv_budget.json. 훅 오류는 작업을 막지 않는다(허용).
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "radar" / "state" / "tv_budget.json"
KST = timezone(timedelta(hours=9))


def cfg():
    try:
        import yaml
        return yaml.safe_load((ROOT / "config" / "tv_budget.yaml").read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def task_of(inp):
    """예약 작업 이름 — 세션 기록 첫머리의 scheduled-task 이름(없으면 사람 세션 = None)"""
    try:
        head = Path(inp.get("transcript_path") or "").read_text(encoding="utf-8", errors="replace")[:6000]
    except Exception:
        return None
    import re
    m = re.search(r'scheduled-task name=\\*"([\w.-]+)', head)
    return m.group(1) if m else None


def deny(msg):
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": msg}}, ensure_ascii=False))


def main(mode):
    try:
        inp = json.load(sys.stdin)
    except Exception:
        inp = {}
    c = cfg()
    now = datetime.now(KST)
    day = (now - timedelta(hours=c.get("day_start_hour", 6))).strftime("%Y-%m-%d")   # 하루 = 06:00 KST부터(동기화가 첫 몫을 쓴다)
    st = load()
    if st.get("day") != day:
        st = {"day": day, "used": 0, "blocked_until": st.get("blocked_until"), "denied": 0}
    tool = str(inp.get("tool_name") or "")
    if mode == "pre":
        bu = st.get("blocked_until")
        if bu and now < datetime.fromisoformat(bu):
            st["denied"] = st.get("denied", 0) + 1
            save(st)
            return deny(f"TradingView 한도 대기 중({bu[11:16]} KST까지) — 부르지 말고 대체 경로(Easyconomics·Fiscal.ai)나 '한도로 못 함'으로 끝낸다(config/tv_budget.yaml)")
        budget = int(c.get("daily_budget", 70))
        # 우선 작업(Analysis 그래프, 2026-11-19 마스터 지시 "Analysis에서 TradingView 그래프를 가져오는 걸 우선순위로")은 예산 전부, 나머지는 우선 몫을 남긴 만큼만
        task = task_of(inp)
        if task:
            st.setdefault("tasks", {})[str(inp.get("session_id"))[:8]] = task
        # 시간대 독점(2026-11-21 마스터 지시 "이번 주 Weekly에 유럽·일본·한국·대만·홍콩 주간 상승률 순위가 빠졌다"):
        # 토요일 07:00~07:15에 다른 세션 3곳이 한도를 먼저 써서 Weekly 지역 스크리너가 막혔다 → 정한 시간대에는 only 작업만 부른다
        for h in c.get("holds") or []:
            if task and now.weekday() in (h.get("weekdays") or []) and h.get("from", "00:00") <= now.strftime("%H:%M") < h.get("until", "24:00") \
                    and not any(str(task or "").startswith(p) for p in h.get("only") or []):
                st["denied"] = st.get("denied", 0) + 1
                save(st)
                return deny(f"TradingView {h.get('from')}~{h.get('until')} KST는 {', '.join(h.get('only') or [])} 몫 — 지금은 부르지 말고 대체 경로를 쓰거나 '한도로 못 함'으로 끝낸다(config/tv_budget.yaml holds)")
        prio = task in (c.get("priority_tasks") or []) or any(now.weekday() in (h.get("weekdays") or []) and str(task or "").startswith(p)
                                                               for h in c.get("holds") or [] for p in h.get("only") or [])
        limit = budget if prio else budget - int(c.get("priority_reserve", 30))
        if st.get("used", 0) >= limit:
            st["denied"] = st.get("denied", 0) + 1
            save(st)
            return deny(f"TradingView 오늘 예산 {st.get('used')}/{budget}건 소진 — 다음 06:00 KST까지 부르지 않는다. 대체 경로를 쓰거나 '한도로 못 함'으로 끝낸다(config/tv_budget.yaml)")
        st["used"] = st.get("used", 0) + 1
        st.setdefault("by_session", {})
        sid = str(inp.get("session_id") or "?")[:8]
        st["by_session"][sid] = st["by_session"].get(sid, 0) + 1
        save(st)
        return None
    resp = json.dumps(inp.get("tool_response") or inp.get("error") or "", ensure_ascii=False)
    if "TOOL_QUOTA_EXCEEDED" in resp or "cooldown" in resp.lower():
        if "daily usage limit" in resp:
            nxt = (now + timedelta(days=1)).replace(hour=c.get("day_start_hour", 6), minute=0, second=0, microsecond=0) if now.hour >= c.get("day_start_hour", 6) else now.replace(hour=c.get("day_start_hour", 6), minute=0, second=0, microsecond=0)
            st["blocked_until"] = nxt.isoformat()
        else:
            st["blocked_until"] = (now + timedelta(minutes=11)).isoformat()
        st["last_quota"] = now.isoformat()
        save(st)
    return None


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        main(sys.argv[1] if len(sys.argv) > 1 else "pre")
    except Exception:
        pass
    sys.exit(0)
