"""모델 사용 한도 관리 — 한도에 걸리면 재개 시각까지 헤드리스 모델 회차를 띄우지 않는다
(마스터 지시 2026-11-24 "Chiip의 데이터 파이프라인이 잘 작동하고 있는지 전반적으로 점검하라 … 고도화할 게 있는지 찾아보고 설계안을 만들어
이를 시스템에 반영하라" — docs/audit/20261124_pipeline_audit.md D1)

점검: 주간·Fable 사용 한도에 걸린 동안(11/23 07시~, 11/24 07:54~ — 둘 다 '16:00 재개') 앱 예약 회차는 모두 바로 실패했다.
  Pulse 문턱(pulse_trigger)은 이를 '앱 예약 정지'로 보고 헤드리스 회차를 3~5분마다 띄웠다. 4초 만에 '종료 코드 1 · 관문 미실행'으로 끝난 회차가
  11/17 34번, 11/23 38번, 11/24 12번이었다. 이 회차들이 하루 상한 40회를 채웠고 '상한 도달'·'앱 정지' 알림이 나갔다.
  노션 감시는 같은 실패를 '처리 실패 — 다시 시도하지 않음'으로 표시해, 마스터가 올린 자료가 다시 읽히지 않았다.
  한도 문구에 재개 시각이 들어 있으니(You've hit your … limit · resets 4pm (Asia/Seoul)) 그때까지 기다리면 된다.
구조:
  · note(text): 모델 출력·오류 문구에서 한도 문구를 찾으면 재개 시각을 radar/state/model_budget.json에 남긴다
  · blocked(now): 재개 전이면 {"until", "kind", "since", "source"}. 헤드리스 실행기(pulse_trigger·run_triage.run_claude·notion_watch·article_draft)가 띄우기 전에 본다
  · guard() / check_failure(text): 대기 중이거나 실패 문구가 한도면 Hold를 던진다 — 실패가 아니라 대기라서, 받는 쪽은 작업을 버리지 않고 재개 뒤 다시 한다
  · alert_once(): 한도 구간마다 한 번만 개인 봇에 알린다
결정론 — 모델 없음. 앱 예약 회차는 앱이 직접 띄우므로 여기서 막지 못한다(한도 동안 앱 회차는 바로 실패해 비용이 들지 않는다).
사용: py radar/model_budget.py            # 지금 상태
      py radar/model_budget.py --clear    # 대기 해제(한도가 먼저 풀렸을 때)
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

STATE = "model_budget"
GRACE_MIN = 3          # 재개 시각 뒤 여유
DEFAULT_HOLD_MIN = 60  # 한도 문구는 있는데 재개 시각을 못 읽으면
MAX_HOLD_DAYS = 8      # 잘못 읽은 날짜로 오래 멈추지 않게
# 앱 예약: "You've hit your Fable limit · resets 4pm (Asia/Seoul)" · 헤드리스(claude -p): "You've reached your Fable limit. Switch to another model…"(재개 시각 없음)
# 옛 문구: "Claude AI usage limit reached|1764000000"(재개 시각 epoch), "5-hour limit reached · resets 3pm"
LIMIT_RES = (re.compile(r"(?:hit|reached)\s+your\s+(?P<kind>[^\n·.]{1,40}?)\s+limit\b(?P<rest>[^\n]{0,160})", re.I),
             re.compile(r"(?P<kind>[\w-]{1,20}(?: [\w-]{1,20})?)\s+limit reached(?P<rest>[^\n]{0,160})", re.I))
EPOCH_RE = re.compile(r"limit reached\|(?P<ts>\d{10})")
EPISODE_GAP_H = 2      # 앞 대기가 끝난 뒤 이 안에 다시 걸리면 같은 한도 구간 — 알림을 다시 보내지 않는다
RESET_RE = re.compile(r"resets\s+(?:(?P<mon>[A-Za-z]{3})[a-z]*\.?\s+(?P<day>\d{1,2}),?\s*)?(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>am|pm)?"
                      r"(?:\s*\((?P<tz>[^)]{1,40})\))?", re.I)
TZ = {"asia/seoul": 9, "kst": 9, "asia/tokyo": 9, "utc": 0, "gmt": 0}
MON = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


class Hold(RuntimeError):
    """모델 사용 한도 대기 — 실패가 아니다. 받는 쪽은 작업을 남겨 두고 재개 뒤 다시 한다"""


def parse(text, now=None):
    """한도 문구 → (종류, 재개 시각 KST) 또는 None. 재개 시각을 못 읽으면 지금 + DEFAULT_HOLD_MIN"""
    now = now or common.now_kst()
    text = str(text or "")
    m = next((x for x in (rx.search(text) for rx in LIMIT_RES) if x), None)
    if not m:
        return None
    kind = re.sub(r"^claude(?: ai)?\s+", "", m.group("kind").strip(), flags=re.I) or "usage"
    e = EPOCH_RE.search(text)
    if e:
        at = datetime.fromtimestamp(int(e.group("ts")), tz=now.tzinfo or timezone(timedelta(hours=9)))
        return kind, min(at, now + timedelta(days=MAX_HOLD_DAYS))
    r = RESET_RE.search(m.group("rest") or "")
    if not r:
        return kind, now + timedelta(minutes=DEFAULT_HOLD_MIN)
    off = TZ.get((r.group("tz") or "Asia/Seoul").strip().lower(), 9)
    tz = timezone(timedelta(hours=off))
    local = now.astimezone(tz)
    h, mi = int(r.group("h")), int(r.group("m") or 0)
    ap = (r.group("ap") or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return kind, now + timedelta(minutes=DEFAULT_HOLD_MIN)
    if r.group("mon") and r.group("mon").lower()[:3] in MON:
        mon, day = MON[r.group("mon").lower()[:3]], int(r.group("day"))
        year = local.year + (1 if mon < local.month - 6 else 0)
        try:
            at = datetime(year, mon, day, h, mi, tzinfo=tz)
        except ValueError:
            return kind, now + timedelta(minutes=DEFAULT_HOLD_MIN)
    else:
        at = local.replace(hour=h, minute=mi, second=0, microsecond=0)
        if at <= local:
            at += timedelta(days=1)
    at = at.astimezone(now.tzinfo or timezone(timedelta(hours=9)))
    return kind, min(at, now + timedelta(days=MAX_HOLD_DAYS))


def note(text, source="", now=None):
    """한도 문구면 대기 상태를 남기고 그 상태를 돌려준다(이미 더 늦은 재개 시각이 있으면 그대로). 아니면 None"""
    now = now or common.now_kst()
    got = parse(text, now)
    if not got:
        return None
    kind, until = got
    known = bool(RESET_RE.search(str(text)) or EPOCH_RE.search(str(text)))
    until = until + timedelta(minutes=GRACE_MIN)
    st = common.load_state(STATE, {})
    cur = st.get("until")
    if cur and datetime.fromisoformat(cur) >= until and datetime.fromisoformat(cur) > now:
        return st
    same = bool(cur) and datetime.fromisoformat(cur) + timedelta(hours=EPISODE_GAP_H) > now   # 같은 한도 구간(재개 시각 없는 1시간 대기가 이어질 때)
    st.update(until=common.iso(until), kind=kind, since=st.get("since") if same and st.get("since") else common.iso(now),
              source=source, text=str(text)[:160], reset_known=known)
    st.setdefault("log", [])
    st["log"] = (st["log"] + [{"at": common.iso(now), "kind": kind, "until": st["until"], "source": source}])[-50:]
    common.save_state(STATE, st)
    common.record_health("model-budget", False, f"사용 한도({kind}) — {st['until'][5:16].replace('T', ' ')} 재개")
    return st


def blocked(now=None):
    """재개 전이면 상태 dict, 아니면 None"""
    now = now or common.now_kst()
    st = common.load_state(STATE, {})
    until = st.get("until")
    try:
        return st if until and datetime.fromisoformat(until) > now else None
    except ValueError:
        return None


def when(st):
    return str(st.get("until") or "")[5:16].replace("T", " ")


def guard(now=None):
    """대기 중이면 Hold — 헤드리스 모델을 띄우기 전에 부른다"""
    st = blocked(now)
    if st:
        raise Hold(f"모델 사용 한도({st.get('kind')}) — {when(st)} 재개 대기")


def check_failure(text, source="", now=None):
    """모델 실패 문구가 한도면 대기를 남기고 Hold를 던진다. 아니면 아무것도 하지 않는다(호출자가 원래 오류를 던진다)"""
    st = note(text, source, now)
    if st:
        raise Hold(f"모델 사용 한도({st.get('kind')}) — {when(st)} 재개 대기")


def alert_once(now=None):
    """한도 구간마다 한 번만 개인 봇에 알린다 → 보냈으면 True"""
    st = blocked(now)
    if not st or st.get("alerted") == st.get("since"):   # 한도 구간(since)마다 한 번
        return False
    eta = f"{when(st)} KST 재개 예정" if st.get("reset_known") else f"재개 시각이 문구에 없어 {DEFAULT_HOLD_MIN}분마다 한 번만 다시 확인합니다"
    try:
        import notify
        notify.send(f"[Chiip Ops] 모델 사용 한도({st.get('kind')}) — {eta}. 그때까지 판단 회차(Pulse·Ten-bagger·Analysis 등)는 "
                    "멈추고 수집은 계속됩니다. 재개 뒤 밀린 자료부터 처리합니다.", "SYSTEM")
    except Exception as exc:
        common.record_health("model-budget", False, f"알림 실패 {type(exc).__name__}")
        return False
    st["alerted"] = st.get("since")
    common.save_state(STATE, st)
    return True


def clear():
    st = common.load_state(STATE, {})
    st.pop("until", None)
    common.save_state(STATE, st)
    common.record_health("model-budget", True)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if "--clear" in argv:
        clear()
        print("대기 해제")
        return 0
    st = blocked()
    print(json.dumps({"blocked": bool(st), **({k: st.get(k) for k in ("kind", "until", "since", "source")} if st else {})}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
