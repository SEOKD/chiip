"""TradingView MCP 하루 호출 예산 훅 (2026-11-19 마스터 지시 "일일 한도가 얼마인지 분석하고 이에 맞춰 일일 주기를 조정하라")

분석(세션 기록 2026-10-30~11-19): 11-14·15·16 KST는 하루 149~194건이 막히지 않았는데, 11-17은 90건째(직전 24시간 97건)에
'daily usage limit + 10-minute cooldown'이 걸렸고 그 뒤 이틀 넘게 냉각이 되풀이됐다(냉각 중에도 회차들이 계속 불러 하루 155건이 막힘).
→ 한도는 고정 일일 건수로 보이지 않는다(며칠 누적 또는 사용 패턴 기반으로 추정 — TradingView가 수치를 공개하지 않아 미확인).
   보수적으로 관측된 가장 낮은 차단점(90)보다 아래인 하루 예산을 코드로 지킨다.
pre  : 오늘(KST) 사용 수가 예산 이상이거나, 한도·냉각 오류 뒤 막힘 시각 전이면 호출 거부(deny). 06:00~07:00 KST 전에는 TradingView 동기화 몫(reserve)을 남긴다.
post : 응답에 TOOL_QUOTA_EXCEEDED가 있으면 막힘 시각 설정 — 냉각이면 11분, 'daily usage limit'이면 다음 날 06:00 KST까지(냉각 중 재시도가 한도를 늘리지 않게).
공용 캐시(2026-11-22 마스터 지시 "TradingView 호출을 효율적으로 하도록 시스템을 다듬어라" — 실제 한도가 하루 11건 안팎인데 세션 6곳이 같은 조회를 되풀이했다):
  post가 읽기 도구(get-·search-·run-screener·technicals) 응답을 radar/state/tv_cache/<키>.json에 저장하고,
  pre가 같은 도구·같은 인자를 TTL(config cache_ttl_min) 안에 다시 부르면 호출 대신 그 파일을 읽으라고 거부한다 — 예산을 쓰지 않는다.
  쓰기 도구(알림·와치리스트·파인 저장)는 캐시하지 않는다. 오늘 도구별 사용 수는 상태 by_tool.
설정 config/tv_budget.yaml, 상태 radar/state/tv_budget.json. 훅 오류는 작업을 막지 않는다(허용).
"""
import hashlib
import re
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


CACHE = ROOT / "radar" / "state" / "tv_cache"
READ = re.compile(r"(get-|search-|run-screener|technicals)")


def short(tool):
    return tool.split("__")[-1].replace("mcp-tv-", "").replace("mcp-watchlist-", "watchlist-")


def cache_key(tool, args):
    return hashlib.sha1((short(tool) + json.dumps(args or {}, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:16]


def ttl_min(c, tool):
    t = c.get("cache_ttl_min") or {}
    return next((float(v) for k, v in t.items() if k != "default" and k in short(tool)), float(t.get("default", 60)))


def cached(c, tool, args, now):
    """→ 유효한 캐시 파일 경로 또는 None"""
    if not READ.search(short(tool)) or not c.get("cache_ttl_min"):
        return None
    f = CACHE / f"{cache_key(tool, args)}.json"
    try:
        at = datetime.fromisoformat(json.loads(f.read_text(encoding="utf-8"))["at"])
    except Exception:
        return None
    return f if now - at < timedelta(minutes=ttl_min(c, tool)) else None


def _head_task(path):
    import re
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(20000)   # 파일 전체가 아니라 첫머리만(세션 기록은 수 MB)
    except Exception:
        return None
    m = re.search(r'scheduled-task name=\\*"([\w.-]+)', head)
    return m.group(1) if m else None


def task_of(inp):
    """예약 작업 이름 — 세션 기록 첫머리의 scheduled-task 이름(없으면 사람 세션 = None).
    서브에이전트 호출은 부모 세션 기록(<세션>/subagents/agent-*.jsonl → <세션>.jsonl, 또는 session_id)으로 찾는다(2026-11-22 마스터 승인 —
    11/15 서브에이전트 152건이 '사람 세션'으로 잡혀 작업별 상한·시간대 독점을 피했다)"""
    tp = Path(str(inp.get("transcript_path") or ""))
    cands = [tp]
    if tp.parent.name == "subagents":
        cands.append(tp.parent.parent.with_suffix(".jsonl"))
    sid = str(inp.get("session_id") or "")
    if sid and tp.parent.exists():
        root = tp.parent.parent if tp.parent.name == "subagents" else tp.parent
        cands.append((root.parent if tp.parent.name == "subagents" else root) / f"{sid}.jsonl")
    for c in cands:
        t = _head_task(c) if str(c) not in ("", ".") else None
        if t:
            return t
    return None


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
        task = task_of(inp)
        if not task:   # 진단(2026-11-22): 11/22 오전 예약 작업 11건이 모두 작업 미식별로 기록됐다 — 받은 경로와 파일 존재 여부를 남긴다
            tp = str(inp.get("transcript_path") or "")
            st["undetected"] = (st.get("undetected", []) + [{"at": now.strftime("%H:%M"), "sid": str(inp.get("session_id"))[:8], "path": tp[-80:], "exists": Path(tp).exists() if tp else False}])[-10:]
        # Proviser는 TradingView를 부르지 않는다(2026-11-22 마스터 지시 "Provisor로 Analysis Report의 주가 반응을 Revised할 때는 TradingView를 이용하지 마라")
        if task and any(str(task).startswith(p) for p in c.get("deny_tasks") or []):
            st["denied"] = st.get("denied", 0) + 1
            save(st)
            return deny(f"{task}는 TradingView를 쓰지 않는다 — 주가 반응·일봉은 knowledge/models/companies/<id>/ohlcv.csv, 모자라면 py radar/market_data.py history <심볼> (Tiingo·Twelve Data·EODHD), 미국 외는 Fiscal.ai company_stock_prices로 읽는다(config/tv_budget.yaml deny_tasks)")
        hit = cached(c, tool, inp.get("tool_input"), now)
        if hit:   # 같은 조회가 TTL 안에 있다 — 예산을 쓰지 않고 파일을 읽게 한다
            st["cache_hits"] = st.get("cache_hits", 0) + 1
            save(st)
            return deny(f"TradingView 같은 조회 캐시 있음({ttl_min(c, tool):.0f}분 이내) — 다시 부르지 말고 Read로 {hit} 의 response를 읽어 쓴다(예산 절약, config/tv_budget.yaml cache_ttl_min)")
        bu = st.get("blocked_until")
        if bu and now < datetime.fromisoformat(bu):
            st["denied"] = st.get("denied", 0) + 1
            save(st)
            return deny(f"TradingView 한도 대기 중({bu[11:16]} KST까지) — 부르지 말고 대체 경로(시세·일봉 py radar/market_data.py quote|history, ETF·스크리너 Easyconomics — py radar/market_data.py --status)나 '한도로 못 함'으로 끝낸다(config/tv_budget.yaml)")
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
                return deny(f"TradingView {h.get('from')}~{h.get('until')} KST는 {', '.join(h.get('only') or [])} 몫 — 지금은 부르지 말고 대체 경로(시세·일봉 py radar/market_data.py quote|history, ETF·스크리너 Easyconomics — py radar/market_data.py --status)를 쓰거나 '한도로 못 함'으로 끝낸다(config/tv_budget.yaml holds)")
        prio = task in (c.get("priority_tasks") or []) or any(now.weekday() in (h.get("weekdays") or []) and str(task or "").startswith(p)
                                                               for h in c.get("holds") or [] for p in h.get("only") or [])
        limit = budget if prio else budget - int(c.get("priority_reserve", 30))
        if st.get("used", 0) >= limit:
            st["denied"] = st.get("denied", 0) + 1
            save(st)
            return deny(f"TradingView 오늘 예산 {st.get('used')}/{budget}건 소진 — 다음 06:00 KST까지 부르지 않는다. 대체 경로(시세·일봉 py radar/market_data.py quote|history, ETF·스크리너 Easyconomics — py radar/market_data.py --status)를 쓰거나 '한도로 못 함'으로 끝낸다(config/tv_budget.yaml)")
        # 작업별 하루 상한(2026-11-22 마스터 지시 "Pulse 줄이기" — 11/16~20 Pulse가 하루 32~103건으로 전체의 절반 이상을 썼다)
        cap = (c.get("task_caps") or {}).get(task) if task else None
        if cap is not None and st.get("by_task", {}).get(task, 0) >= int(cap):
            st["denied"] = st.get("denied", 0) + 1
            save(st)
            return deny(f"TradingView {task} 오늘 몫 {cap}건 소진 — 부르지 말고 대체 경로(시세·일봉 py radar/market_data.py quote|history, ETF·스크리너 Easyconomics — py radar/market_data.py --status)를 쓰거나 그 줄을 빼고 끝낸다(config/tv_budget.yaml task_caps)")
        tcap = (c.get("tool_caps") or {}).get(short(tool))
        if tcap is not None and st.get("by_tool", {}).get(short(tool), 0) >= int(tcap):
            st["denied"] = st.get("denied", 0) + 1
            save(st)
            return deny(f"TradingView {short(tool)} 오늘 몫 {tcap}건 소진 — 알림은 만들지 말고 리포트·피드에 가격 문턱만 적는다(config/tv_budget.yaml tool_caps)")
        if task:
            st.setdefault("by_task", {})[task] = st.get("by_task", {}).get(task, 0) + 1
        st["used"] = st.get("used", 0) + 1
        st.setdefault("by_tool", {})[short(tool)] = st.get("by_tool", {}).get(short(tool), 0) + 1
        st.setdefault("by_session", {})
        sid = str(inp.get("session_id") or "?")[:8]
        st["by_session"][sid] = st["by_session"].get(sid, 0) + 1
        save(st)
        return None
    resp = json.dumps(inp.get("tool_response") or inp.get("error") or "", ensure_ascii=False)
    if "TOOL_QUOTA_EXCEEDED" in resp or "cooldown" in resp.lower():
        if "daily usage limit" in resp:   # 2026-11-21: 다음 06시에 풀면 곧바로 다시 걸렸다 → 걸린 뒤 block_hours_after_daily시간 쉰다
            st["blocked_until"] = (now + timedelta(hours=float(c.get("block_hours_after_daily", 24)))).isoformat()
        else:
            st["blocked_until"] = (now + timedelta(minutes=11)).isoformat()
        st["last_quota"] = now.isoformat()
        save(st)
    elif mode == "post" and READ.search(short(tool)) and inp.get("tool_response") and '"isError": true' not in resp:
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / f"{cache_key(tool, inp.get('tool_input'))}.json").write_text(json.dumps(
            {"at": now.isoformat(), "tool": short(tool), "args": inp.get("tool_input"), "response": inp.get("tool_response")}, ensure_ascii=False), encoding="utf-8")
    return None


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        main(sys.argv[1] if len(sys.argv) > 1 else "pre")
    except Exception:
        pass
    sys.exit(0)
