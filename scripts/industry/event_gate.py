"""Industry 사건 인뎁스 관문 — 산업을 흔드는 사건이 있었나 (마스터 지시 2026-11-08 "이벤트 발생 시, 분기 마감 시 산업 인뎁스 작성도 Indepth Weekly에 포함")

결정론으로 후보만 고른다. 판단(정말 산업 판단을 바꾸는가)과 글은 모델 — 스킬 industry-event.
입력: radar/state/alerts.json(Pulse가 보낸 P0·P1 알림, entities = 유니버스 id), 산업 묶음 = weekly_pick.cfg() + 세그먼트 풀 산업(industry_quarter.industries()).
후보 규칙(config/industry_logic.yaml event_gate):
  ① 규제·정책 알림이 묶음 종목을 하나라도 건드림   ② P0 알림   ③ 창(기본 48시간) 안 P0·P1 알림이 같은 묶음의 서로 다른 종목 min_members곳 이상
같은 산업은 cooldown_days(기본 14일) 안에 다시 후보로 올리지 않는다(radar/state/industry_event_gate.json).
사용: py scripts/industry/event_gate.py [--done <산업>]   → {"due", "candidates": [{industry, name, why, alerts}]}
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "radar"))
KST = timezone(timedelta(hours=9))
ALERTS = ROOT / "radar" / "state" / "alerts.json"
STATE = ROOT / "radar" / "state" / "industry_event_gate.json"
DEFAULT = {"window_hours": 48, "min_members": 2, "cooldown_days": 14, "policy_types": ["규제·정책"], "max_candidates": 3}


def cfg():
    c = (yaml.safe_load((ROOT / "config" / "industry_logic.yaml").read_text(encoding="utf-8")) or {}).get("event_gate") or {}
    return {**DEFAULT, **c}


def _load(p, default):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def groups():
    """{산업 id: (이름, 종목 id 집합)}"""
    import industry_quarter as IQ
    mem = IQ.members()
    return {k: (IQ.industry_name(k), {m["id"] for m in mem.get(k) or []}) for k in IQ.industries()}


def _ts(s):
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=KST)
    except ValueError:
        return None


def check(now=None, alerts=None, gs=None, c=None):
    c = c or cfg()
    now = now or datetime.now(KST)
    alerts = alerts if alerts is not None else _load(ALERTS, {})
    gs = gs if gs is not None else groups()
    st = _load(STATE, {})
    since = now - timedelta(hours=c["window_hours"])
    recent = [a for a in alerts.values() if a.get("level") in ("P0", "P1") and (_ts(a.get("sent_at")) or since) > since]
    out = []
    for gid, (name, ids) in gs.items():
        last = st.get(gid)
        if last and (_ts(last) or now) > now - timedelta(days=c["cooldown_days"]):
            continue
        hit = [a for a in recent if set(a.get("entities") or []) & ids]
        if not hit:
            continue
        why = []
        if any(a.get("doc_type") in c["policy_types"] for a in hit):
            why.append("규제·정책")
        if any(a.get("level") == "P0" for a in hit):
            why.append("P0")
        touched = {e for a in hit for e in (a.get("entities") or []) if e in ids}
        if len(touched) >= c["min_members"]:
            why.append(f"종목 {len(touched)}곳 동시")
        if why:
            out.append({"industry": gid, "name": name, "why": why, "score": len(why) * 10 + len(touched),
                        "alerts": [{"title": a.get("title"), "level": a.get("level"), "doc_type": a.get("doc_type"), "url": a.get("url")} for a in hit[:6]]})
    out.sort(key=lambda x: -x["score"])
    return {"due": bool(out), "candidates": out[:c["max_candidates"]], "at": now.isoformat(timespec="minutes")}


def done(industry, now=None):
    st = _load(STATE, {})
    st[industry] = (now or datetime.now(KST)).isoformat(timespec="minutes")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if argv[:1] == ["--done"]:
        done(argv[1])
        print(f"[사건 인뎁스] {argv[1]} 작성 표시")
        return 0
    print(json.dumps(check(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
