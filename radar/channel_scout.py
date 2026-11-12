"""데이터 파이프라인 채널 탐색 장부 (마스터 지시 2026-11-01 "Proviser는 작동할 때마다 데이터 파이프라인 채널을 찾도록 해라. 이 구조를 엔진에 넣어놔라")

Proviser 회차마다 후보 채널과 약관·robots.txt 확인 결과, 판단과 사유를 한 줄 이상 남긴다. 기록이 없으면 그 회차를 미완료로 적는다.
run()은 run_hourly가 매시간 부른다. 모델 없이 지난 회차를 점검하고 장부에 '미완료'·'미실행'을 쓴다. Proviser가 필요하다고 판단한 채널은 동의 없이 연결하고 decision '연결'로 적는다(2026-11-08 마스터 지시). 키·유료·로그인 채널도 수집기까지 연결해 두고(키 대기) 가입·결제만 마스터 몫으로 TODO_MASTER에 남긴다.
사용: py radar/channel_scout.py --review          # 회차 시작: 오늘 분야·이전 후보·미완료
      py radar/channel_scout.py --add <json 파일>  # [{channel, area, access, robots, terms, needs, decision, reason, url}]
      py radar/channel_scout.py --check            # 이번 회차 기록이 없으면 종료 코드 1 — Proviser 텔레그램 전에 돌린다
"""
import argparse
import csv
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pollers import common  # noqa: E402

STORE = common.ROOT / "knowledge" / "models" / "channels" / "scout.csv"
SCORES = common.ROOT / "docs" / "proviser" / "scores.csv"
STATE = "channel_scout"
FIELDS = ["date", "channel", "area", "access", "robots", "terms", "needs", "decision", "reason", "url"]
ROLLOVER_H = 6     # Proviser는 23시에 시작해 자정을 넘길 수 있다 — 06시 전은 전날 회차
CHECK_FROM_H = 8   # 회차가 끝났을 시각


def config():
    return common.load_yaml("config/data_channels.yaml")


def run_day(now=None):
    now = now or common.now_kst()
    return (now.date() - timedelta(days=1 if now.hour < ROLLOVER_H else 0)).isoformat()


def read(path=STORE):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write(rows, path=STORE):
    path.parent.mkdir(parents=True, exist_ok=True)
    head = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if head:
            w.writeheader()
        w.writerows(rows)


def problems(r, cfg):
    """저장할 수 없는 이유. 약관 확인이 없거나, 금지·승인 필요 채널을 채택 제안으로 쓰면 받지 않는다"""
    need = ("channel", "reason", "decision") if r.get("decision") == "없음" else ("channel", "area", "access", "robots", "terms", "needs", "decision", "reason")
    out = [f"{k} 없음" for k in need if not r.get(k)]
    if out:
        return out
    if r["decision"] == "없음":
        return []
    for k, allowed in (("decision", cfg["decisions"]), ("robots", cfg["robots"]), ("terms", cfg["terms"]), ("needs", cfg["needs"])):
        if r[k] not in allowed:
            out.append(f"{k} {r[k]}")
    if r["area"] not in cfg["areas"]:
        out.append(f"분야 {r['area']}")
    if r["decision"] in ("채택 제안", "연결") and (r["robots"] == "금지" or r["terms"] in ("금지", "미확인")):
        out.append(f"약관·robots 미통과는 {r['decision']} 불가")
    if r["decision"] == "연결":   # 마스터 지시 2026-11-08 — 동의 없이 연결하되, 연결한 수집기가 실제로 있어야 기록한다
        mods = [m for m in re.findall(r"(?:radar|scripts)/[\w/]+\.py", r.get("reason", "")) if (common.ROOT / m).exists()]
        if not mods:
            out.append("연결은 reason에 실제 수집기 경로(radar/… 또는 scripts/….py)가 있어야 한다")
        # 키·유료·로그인 채널도 수집기까지 연결해 둔다(키 대기) — 키 이름(.env)을 적고, 키가 들어오면 스스로 켜진다. 가입·결제는 마스터 몫
        if r["needs"] != "없음" and not re.search(r"\b[A-Z][A-Z0-9_]*_(?:KEY|TOKEN|USER|SECRET)\b", r.get("reason", "")):
            out.append("키 대기 연결은 reason에 .env 키 이름(예: LDA_API_KEY)을 적는다")
    if r["needs"] != "없음" and r["decision"] not in ("승인 대기", "기각", "연결"):
        out.append("유료·키·로그인 채널은 연결(키 대기)·승인 대기·기각만")
    if r["decision"] == "승인 대기" and r["needs"] == "없음":
        out.append("승인이 필요한 조건이 없다")
    return out


def add(path, store=STORE, day=None):
    text = Path(path).read_text(encoding="utf-8")
    rows = json.loads(text[text.index("["):text.rindex("]") + 1])
    cfg, ok, bad = config(), [], []
    day = day or run_day()
    for r in rows:
        why = problems(r, cfg)
        if why:
            bad.append(f"{r.get('channel')}: {', '.join(why)}")
        else:
            ok.append({**{k: r.get(k, "") for k in FIELDS}, "date": day})
    write(ok, store)
    return len(ok), bad


def recorded(day, rows):
    return any(r["date"] == day and r["decision"] not in ("미완료", "미실행") for r in rows)


def ran(day, path=SCORES):
    if not path.exists():
        return False
    with path.open(encoding="utf-8", newline="") as f:
        return any(r.get("date") == day for r in csv.DictReader(f))


def audit(day, rows, did_run):
    """그 회차의 판정 행. 기록이 있으면 None"""
    if recorded(day, rows):
        return None
    status, why = ("미완료", "회차는 돌았으나 채널 탐색 기록이 없다") if did_run else ("미실행", "Proviser 회차 기록이 없다")
    return {**{k: "" for k in FIELDS}, "date": day, "channel": "-", "decision": status, "reason": why}


def days_to_check(last, today, start):
    """아직 판정하지 않은 지난 회차 날짜"""
    d = date.fromisoformat(max(last or "", start)) + (timedelta(days=1) if last and last >= start else timedelta(days=0))
    while d < today:
        yield d.isoformat()
        d += timedelta(days=1)


def run(now=None):
    """run_hourly용 — 08시 이후 어제까지의 회차를 판정한다"""
    now = now or common.now_kst()
    if now.hour < CHECK_FROM_H:
        return 0, 0
    st, rows = common.load_state(STATE, {}), read()
    start = config()["start"]
    bad = 0
    for day in days_to_check(st.get("checked"), now.date(), start):
        row = audit(day, rows, ran(day))
        if row:
            write([row])
            rows.append(row)
            bad += 1
        st["checked"] = day
    common.save_state(STATE, st)
    return bad, 0


def focus(day, areas):
    """오늘 먼저 볼 분야 — 날짜마다 돌아간다"""
    return areas[date.fromisoformat(day).toordinal() % len(areas)]


def review():
    cfg, rows, day = config(), read(), run_day()
    print(f"[데이터 채널 탐색] 회차 {day} · 오늘 분야: {focus(day, cfg['areas'])}")
    seen = sorted({r["channel"] for r in rows if r["channel"] not in ("-", "없음")})
    print("이미 본 채널: " + (" · ".join(seen) or "없음"))
    wait = [f"{r['channel']}({r['needs']})" for i, r in enumerate(rows) if r["decision"] == "승인 대기"
            and not any(x["channel"] in (r["channel"], r["channel"][:len(x["channel"])]) and x["decision"] in ("연결", "기각") for x in rows[i + 1:])]
    if wait:
        print("마스터 승인 대기: " + " · ".join(dict.fromkeys(wait)))
    miss = [f"{r['date']} {r['decision']}" for r in rows if r["decision"] in ("미완료", "미실행")][-5:]
    if miss:
        print("지난 회차 누락: " + " · ".join(miss))


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--add")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    if a.add:
        n, bad = add(a.add)
        print(f"[데이터 채널 탐색] 기록 {n}줄" + (f" · 거절 {bad}" if bad else ""))
        return 1 if bad and not n else 0
    if a.check:
        ok = recorded(run_day(), read())
        print("[데이터 채널 탐색] " + ("이번 회차 기록 있음" if ok else "기록 없음 — 지시문 6-5를 먼저 끝낸다"))
        return 0 if ok else 1
    if a.review:
        review()
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
