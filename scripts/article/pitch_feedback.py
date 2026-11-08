"""기사 소재 채택 버튼 (2026-11-08 마스터 지시 "기사 소재 전달 시스템을 점검하고 보완")

점검 결과: outputs/article/pitch/log.csv의 adopted 칸에 입력 경로가 없어 열흘 동안 한 번도 채워지지 않았다 — 채택률 KPI가 0으로 잡혀
프로바이저 점수가 측정 결함으로 깎였다(10/30~11/7 반복 지적). 텔레그램 기사 소재 1통 아래에 버튼을 단다:
  [① 채택] [② 채택] [③ 채택]
  [모두 패스]
누르면 radar/telegram_inbox.py(run_poll이 5분마다)가 이 모듈의 on_callback을 불러 log.csv adopted를 채운다('채택 YYYY-MM-DD HH:MM' 또는 '패스').
다시 누르면 덮어쓴다. 답하지 않은 칸은 비워 두고, 프로바이저는 답한 칸만 분모로 센다.
사용: py scripts/article/pitch_feedback.py send <YYYYMMDD>   # outputs/article/pitch/<날짜>_tg.txt를 버튼과 함께 보낸다(예약 작업 3단계)
"""
import csv
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG = ROOT / "outputs" / "article" / "pitch" / "log.csv"
KST = timezone(timedelta(hours=9))
CIRCLED = "①②③④⑤"


def count(text):
    return len(re.findall(r"(?m)^기사[①②③④⑤]", text))


def buttons(day, n):
    row = [(f"{CIRCLED[i]} 채택", f"pitch:{day}:{i + 1}:y") for i in range(n)]
    return [row, [("모두 패스", f"pitch:{day}:0:n")]]


def send(day):
    sys.path.insert(0, str(ROOT / "radar"))
    import notify
    text = (ROOT / "outputs" / "article" / "pitch" / f"{day}_tg.txt").read_text(encoding="utf-8")
    return notify.send(text, "PITCH", buttons=buttons(day, max(1, count(text))))


def mark(day, n, verdict, log=LOG):
    """log.csv의 그날 n번째(0이면 그날 전부) adopted를 채운다 → 바꾼 줄 수"""
    if not log.exists():
        return 0
    with log.open(encoding="utf-8", newline="") as f:
        rd = csv.DictReader(f)
        rows, fields = list(rd), rd.fieldnames
    date_s = f"{day[:4]}-{day[4:6]}-{day[6:]}"
    stamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    hit = 0
    for r in rows:
        pid = r.get("pitch_id") or ""
        if r.get("date") == date_s and (n == 0 or pid.endswith(f"-{n:02d}")):
            r["adopted"] = f"채택 {stamp}" if verdict == "y" else "패스"
            hit += 1
    with log.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)
    return hit


def on_callback(data, log=LOG):
    """'pitch:YYYYMMDD:n:y|n' → (알림 문구, 새 버튼 줄 또는 None)"""
    _, day, n, v = data.split(":")
    hit = mark(day, int(n), v, log)
    if not hit:
        return "기록을 찾지 못함(log.csv)", None
    note = "모두 패스로 기록" if int(n) == 0 else f"{CIRCLED[int(n) - 1]} 채택으로 기록"
    return note, {"inline_keyboard": [[{"text": f"✅ {note}", "callback_data": "noop"}]]}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) >= 2 and argv[0] == "send":
        print("[기사 소재] 발송" if send(argv[1]) else "[기사 소재] 발송 실패")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
