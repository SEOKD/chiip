"""API 키·토큰 만료 알림 (마스터 지시 2026-11-22, 설정 config/api_keys.yaml)

만료일이 있는 키(issued + valid_days 또는 expires)는 만료 remind_days 전마다 한 번씩, 만료일을 모르는 키는 연결 수집기의 인증 오류가 연속될 때
마스터 개인 봇(Chiip Pulse 표기)으로 알린다. 키 값은 다루지 않는다 — 이름이 .env에 있는지만 본다(load_env).
하루 1회(run_hourly), 알린 기록 radar/state/key_expiry.json.
사용: py radar/key_expiry.py [--status] [--dry]
"""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

SOURCE_ID = "key-expiry"
STATE = "key_expiry"
AUTH_RE = re.compile(r"\b(401|403|503)\b|unauthor|forbidden|invalid.?(api)?.?key|expired|token", re.I)


def cfg():
    return common.load_yaml("config/api_keys.yaml")


def expiry(k):
    if k.get("expires"):
        return date.fromisoformat(str(k["expires"]))
    if k.get("issued") and k.get("valid_days"):
        return date.fromisoformat(str(k["issued"])) + timedelta(days=int(k["valid_days"]))
    return None


def due(k, c, today, sent):
    """(알림 문구 또는 None, 기록 표시) — 만료까지 남은 날이 remind_days 문턱을 처음 넘었을 때만"""
    exp = expiry(k)
    if not exp:
        return None, None
    left = (exp - today).days
    hit = [d for d in sorted(c["remind_days"]) if left <= d]
    if not hit:
        return None, None
    mark = f"{k['env']}|{exp.isoformat()}|{hit[0]}"
    if mark in sent:
        return None, None
    when = f"{left}일 남음" if left > 0 else ("오늘 만료" if left == 0 else f"{-left}일 지남")
    return (f"🔑 {k['name']} 만료 {exp.isoformat()}({when})\n쓰는 곳: {k.get('used_by', '')}\n다시 받는 법: {k.get('how', '')}\n"
            f"새로 받으면 config/api_keys.yaml의 issued를 그 날짜로 고친다"), mark


def auth_trouble(k, c, health, today, sent):
    for sid in k.get("health") or []:
        h = health.get(sid) or {}
        if int(h.get("error_count") or 0) >= int(c.get("auth_error_count", 3)) and AUTH_RE.search(str(h.get("last_error") or "")):
            mark = f"{k['env']}|auth|{today.isoformat()[:7]}|{sid}"   # 같은 달·같은 수집기는 한 번
            if mark not in sent:
                return (f"🔑 {k['name']} 확인 필요 — {sid} 인증 오류 {h['error_count']}회 연속\n쓰는 곳: {k.get('used_by', '')}\n"
                        f"다시 받는 법: {k.get('how', '')}"), mark
    return None, None


def check(today=None, env=None, health=None, sent=None):
    c = cfg()
    today = today or common.now_kst().date()
    env = common.load_env() if env is None else env
    health = common.load_state("health") if health is None else health
    sent = set(sent or [])
    out = []
    for k in c["keys"]:
        if not env.get(k["env"]):
            continue   # 아직 넣지 않은 키는 알리지 않는다(키 대기는 TODO_MASTER 몫)
        for msg, mark in (due(k, c, today, sent), auth_trouble(k, c, health or {}, today, sent)):
            if msg:
                out.append((msg, mark))
    return out


def status(today=None):
    today = today or common.now_kst().date()
    env = common.load_env()
    rows = []
    for k in cfg()["keys"]:
        exp = expiry(k)
        when = f"{exp.isoformat()}({(exp - today).days}일 남음)" if exp else "미확인"
        rows.append(f"{k['env']}: {'있음' if env.get(k['env']) else '없음'} · 만료 {when}")
    return rows


def run(dry=False):
    st = common.load_state(STATE) or {}
    sent = st.get("sent") or []
    found = check(sent=sent)
    if found and not dry:
        import notify
        ok = notify.send("[Chiip Pulse] API 키 갱신 알림\n\n" + "\n\n".join(m for m, _ in found), "P1")
        if ok:
            st["sent"] = (sent + [mk for _, mk in found])[-500:]
            common.save_state(STATE, st)
    common.record_health(SOURCE_ID, True, None)
    return {"alerts": len(found), "dry": [m for m, _ in found] if dry else None}, 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--status" in sys.argv:
        print("\n".join(status()))
    else:
        print(json.dumps(run(dry="--dry" in sys.argv)[0], ensure_ascii=False))
