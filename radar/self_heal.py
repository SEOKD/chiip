"""수집 채널 자가 복구 (마스터 지시 2026-11-02 "무역, PPI 등 통계 지표뿐 아니라 텔레그램 채널 정보 수집, Fiscal.ai와 Zacks 등 재무 데이터 채널 등
에이전트의 데이터 수집 파이프라인 채널 중 이상이 생기면 스스로 문제를 해결하는 구조를 넣어라")

run_hourly가 한 시간마다 돈다(모델 없음). 복구 단계:
  1 탐지   health.json 연속 오류, 산출물 신선도, 텔레그램 수집 점수, 모델이 보고한 MCP 장애(--report)
  2 분류   key(키·권한) · rate(호출 제한) · network(일시 장애) · schema(응답 형식 변경) · stale(갱신 멈춤) · unknown
  3 자동   수집기를 간격을 늘려 다시 돌린다. rate·network 장애 채널은 source_router가 잠시 건너뛰고 다음 채널로 넘어간다
  4 모델   재시도로 안 풀리면 repair 대기열에 넣고 Pulse 회차가 원인을 찾아 고친다(docs/tasks/chiip-pulse.md 1-1 i)
  5 보고   key 장애와 모델도 못 고친 건만 텔레그램으로 한 번 알리고 docs/TODO_MASTER.md 확인을 부탁한다. 저절로 풀린 건은 보내지 않는다

사용: py radar/self_heal.py --status · --report fiscal "오류 내용" · --resolved <채널> "고친 것" · --failed <채널> "못 고친 이유"
"""
import argparse
import importlib
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

CONFIG = common.ROOT / "config" / "pipeline_health.yaml"
STATE = "self_heal"
DOWN = "channel_down"   # source_router가 읽는다


def config():
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def classify(text):
    t = str(text)
    if re.search(r"키 없음|[A-Z_/]{3,} 없음|\b401\b|\b403\b|NOT_REGISTERED|Unauthorized|Forbidden|invalid.{0,12}key", t, re.I):
        return "key"
    if re.search(r"\b429\b|rate.?limit|too many|한도|weekly limit", t, re.I):
        return "rate"
    if re.search(r"timed? ?out|URLError|ConnectionError|ConnectionReset|RemoteDisconnected|\b50[0-4]\b|IncompleteRead|ssl", t, re.I):
        return "network"
    if re.search(r"JSONDecode|KeyError|IndexError|ParseError|\b404\b|형식|StopIteration|TypeError|ValueError", t):
        return "schema"
    return "unknown"


def age_hours(path, now):
    return (now.timestamp() - path.stat().st_mtime) / 3600 if path.exists() else None


def detect(now, cfg):
    """{채널: 문제 설명}"""
    out = {}
    skip = set(cfg.get("ignore") or [])
    for sid, h in common.load_state("health").items():
        if h.get("error_count", 0) >= cfg["error_count"] and sid not in skip:
            out[sid] = str(h.get("last_error") or "오류")
    for c in cfg.get("files") or []:
        p = common.ROOT / c["path"]
        age = age_hours(p, now)
        if age is None or age > c["max_age_h"]:
            out[c["id"]] = f"stale: {c['path']} {'없음' if age is None else f'{age:.0f}시간 묵음'}"
    try:
        latest = json.loads((common.ROOT / "knowledge/models/trade_ppi/latest.json").read_text(encoding="utf-8"))
        if latest.get("errors"):
            out.setdefault("trade-ppi", "; ".join(latest["errors"][:4]))
    except (OSError, ValueError):
        pass
    try:
        from pollers import tg_channels
        score = tg_channels.score(now)
        if score[0] < cfg["telegram_min_score"]:
            out["tg-channels"] = f"stale: 수집 점수 {score[0]} {score[1]}"
    except Exception as exc:
        out["tg-channels"] = f"{type(exc).__name__}: {exc}"
    st = common.load_state(STATE, {})
    for ch, r in (st.get("reported") or {}).items():
        if datetime.fromisoformat(r["at"]) > now - timedelta(hours=cfg["report_keep_h"]):
            out[ch] = r["error"]
    return out


def retry(job, cfg):
    """수집기를 한 번 다시 돈다. 성공하면 True"""
    mod = (cfg.get("jobs") or {}).get(job)
    if not mod:
        return False
    try:
        if mod == "tg_channels":
            from pollers import tg_channels
            tg_channels.poll_if_stale()
        else:
            importlib.import_module(mod).run()
        common.record_health(job, True)
        return True
    except Exception as exc:
        common.record_health(job, False, f"{type(exc).__name__}: {exc}")
        return False


def plan(entry, kind, now, cfg):
    """다음 조치 — retry / wait / repair / master. entry: attempts, next_at, repair_at"""
    if entry.get("gave_up"):
        return "wait"
    if kind == "key":
        return "master"
    if entry.get("next_at") and datetime.fromisoformat(entry["next_at"]) > now:
        return "wait"
    return "retry" if entry.get("attempts", 0) < cfg["max_retries"] else "repair"


def run(now=None, cfg=None):
    now, cfg = now or common.now_kst(), cfg or config()
    st = common.load_state(STATE, {})
    items, down, sent = st.setdefault("items", {}), {}, 0
    found = detect(now, cfg)
    for ch in [c for c in items if c not in found]:   # 저절로 풀렸다. 조용히 지운다
        st.setdefault("history", []).append({"channel": ch, "at": common.iso(now), "how": "자동 복구", "kind": items[ch].get("kind")})
        del items[ch]
    for ch, why in found.items():
        kind = "stale" if str(why).startswith("stale") else classify(why)
        e = items.setdefault(ch, {"since": common.iso(now), "attempts": 0})
        e.update({"kind": kind, "why": str(why)[:240]})
        if ch in cfg.get("routed", []) and kind in ("rate", "network", "unknown"):
            down[ch] = common.iso(now + timedelta(hours=cfg["route_hold_h"]))
        step = plan(e, kind, now, cfg)
        if step == "retry":
            e["attempts"] += 1
            e["next_at"] = common.iso(now + timedelta(hours=2 ** e["attempts"]))
            if retry(ch, cfg) and ch != "tg-channels":
                common.record_health(ch, True)
        elif step == "repair" and not e.get("repair_at"):
            e["repair_at"] = common.iso(now)
        elif step == "master" and not e.get("told"):
            e["told"] = common.iso(now)
            sent += tell(ch, e, "키나 권한이 필요합니다")
    st["history"] = (st.get("history") or [])[-100:]
    common.save_state(STATE, st)
    common.save_state(DOWN, down)
    return f"문제 {len(found)}건, 모델 대기 {sum(1 for e in items.values() if e.get('repair_at') and not e.get('gave_up'))}건, 알림 {sent}건"


def tell(ch, e, what):
    import notify
    try:
        notify.send(f"Chiip 수집 채널 이상: {ch}\n- 상태: {what}\n- 내용: {e.get('why', '')[:160]}\n- 할 일: docs/TODO_MASTER.md 또는 설정 확인", "P2")
        return 1
    except Exception:
        return 0


def status(now=None):
    """Pulse 관문이 부른다 — 모델이 고칠 건이 있으면 한 건만 연다"""
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    hold = st.get("hold")
    if hold and datetime.fromisoformat(hold) > now:
        return {"due": False}
    todo = [{"channel": c, **{k: e.get(k) for k in ("kind", "why", "since", "attempts")}} for c, e in (st.get("items") or {}).items() if e.get("repair_at") and not e.get("gave_up")]
    return {"due": bool(todo), "items": todo[:1]}


def offered(now=None, hours=6):
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    st["hold"] = common.iso(now + timedelta(hours=hours))
    common.save_state(STATE, st)


def report(channel, error, now=None):
    """모델이 MCP 장애를 만났을 때 — Fiscal.ai·Zacks·Easyconomics는 스크립트가 직접 부르지 못해 모델이 알린다"""
    st = common.load_state(STATE, {})
    st.setdefault("reported", {})[channel] = {"at": common.iso(now or common.now_kst()), "error": str(error)[:240]}
    common.save_state(STATE, st)


def finish(channel, note, fixed, now=None):
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    e = (st.get("items") or {}).get(channel)
    if e is None:
        return f"{channel}: 대기 항목 없음"
    st.setdefault("history", []).append({"channel": channel, "at": common.iso(now), "how": note[:200], "kind": e.get("kind")})
    (st.get("reported") or {}).pop(channel, None)
    if fixed:
        del st["items"][channel]
    else:
        e["gave_up"] = common.iso(now)
        tell(channel, e, f"자동 복구 실패: {note[:120]}")
    common.save_state(STATE, st)
    return f"{channel}: 기록"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--report", nargs=2, metavar=("채널", "오류"))
    ap.add_argument("--resolved", nargs=2, metavar=("채널", "고친 것"))
    ap.add_argument("--failed", nargs=2, metavar=("채널", "이유"))
    a = ap.parse_args()
    if a.report:
        report(*a.report)
        print("기록")
    if a.resolved:
        print(finish(*a.resolved, True))
    if a.failed:
        print(finish(*a.failed, False))
    if a.run:
        print(run())
    if a.status:
        st = common.load_state(STATE, {})
        for c, e in (st.get("items") or {}).items():
            print(c, e.get("kind"), f"시도 {e.get('attempts')}", "모델 대기" if e.get("repair_at") else "", e.get("why", "")[:110])
        print("우회 중:", common.load_state(DOWN, {}))


if __name__ == "__main__":
    main()
