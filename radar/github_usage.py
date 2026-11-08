"""GitHub 사용량 95% 경보 → Pulse (마스터 지시 2026-11-08 "Github 용량이 요금 부과까지 95% 진척된 경우 Pulse로 알려달라")

API 토큰 없이 저장소에서 추정한다(설정 config/github_usage.yaml):
  ① Actions 실행 시간 — 이번 달 main에 올라간 커밋 수(first-parent, 푸시 횟수의 상한) × 1회 분 ÷ 월 무료 분
  ② 저장소 크기 — git count-objects의 압축 크기 + 느슨한 객체 ÷ 권장 1GB(요금 아님 — 참고 경보)
95%를 넘은 항목은 한 달에 한 번 Pulse(텔레그램 개인 봇)로 알린다. radar/pulse.py가 하루 한 번 부른다(모델 없이 결정론).
사용: py radar/github_usage.py [--check] [--send]
"""
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common  # noqa: E402

KST = timezone(timedelta(hours=9))
STATE = "github_usage"


def cfg():
    return yaml.safe_load((ROOT / "config" / "github_usage.yaml").read_text(encoding="utf-8"))


def _git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, encoding="utf-8").stdout


def measure(now=None, c=None):
    c = c or cfg()
    now = now or datetime.now(KST)
    month0 = now.strftime("%Y-%m-01")
    runs = 0
    for b in c["branches"]:
        ref = f"origin/{b}" if _git("rev-parse", "--verify", "--quiet", f"origin/{b}").strip() else b
        runs += len([x for x in _git("log", "--first-parent", f"--since={month0} 00:00", "--format=%H", ref).splitlines() if x.strip()])
    minutes = runs * c["minutes_per_run"]
    kv = dict(line.split(": ", 1) for line in _git("count-objects", "-v").splitlines() if ": " in line)
    mb = (int(kv.get("size-pack", 0)) + int(kv.get("size", 0))) / 1024
    return {"month": month0[:7], "runs": runs, "actions_min": round(minutes), "actions_share": minutes / c["actions_free_minutes"],
            "repo_mb": round(mb, 1), "repo_share": mb / c["repo_soft_mb"]}


def message(m, items, c=None):
    c = c or cfg()
    L = ["[Chiip Pulse · GitHub 사용량 경보]", ""]
    if "actions" in items:
        L.append(f"⚠ Actions 실행 시간 {m['actions_share']:.0%} — 이번 달 추정 {m['actions_min']:,}분 / 무료 {c['actions_free_minutes']:,}분(main 푸시 {m['runs']}회 × {c['minutes_per_run']}분, 상한 추정). 넘으면 분당 요금이 붙는다.")
    if "repo" in items:
        L.append(f"⚠ 저장소 크기 {m['repo_share']:.0%} — {m['repo_mb']:,}MB / 권장 {c['repo_soft_mb']:,}MB. 요금은 없지만 정리(이미지 링크 방식·Git LFS)를 검토할 때다.")
    L += ["", "정확한 값: github.com → Settings → Billing and plans → Usage"]
    return "\n".join(L)


def check(now=None, send=False, c=None):
    """95%를 넘은 항목 — send면 이번 달 처음일 때만 Pulse로 보낸다"""
    c = c or cfg()
    now = now or datetime.now(KST)
    m = measure(now, c)
    items = [k for k in ("actions", "repo") if m[f"{k}_share"] >= c["alert_at"]]
    st = common.load_state(STATE, {})
    new = [k for k in items if st.get(k) != m["month"]]
    sent = False
    if send and new:
        import notify
        sent = bool(notify.send(message(m, new, c), "PULSE"))
        if sent:
            for k in new:
                st[k] = m["month"]
    st["last_check"] = now.isoformat(timespec="minutes")
    st["last"] = m
    common.save_state(STATE, st)
    return m, items, sent


def due(now=None):
    """하루 한 번"""
    now = now or datetime.now(KST)
    last = common.load_state(STATE, {}).get("last_check")
    return not last or datetime.fromisoformat(last) < now - timedelta(hours=24)


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    m, items, sent = check(send="--send" in argv)
    print(f"[GitHub 사용량] {m['month']} Actions 추정 {m['actions_min']}분({m['actions_share']:.0%}, 푸시 {m['runs']}회) · 저장소 {m['repo_mb']}MB({m['repo_share']:.0%})"
          + (f" · 95% 넘음: {items}{' — 발송' if sent else ''}" if items else " · 경보 없음"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
