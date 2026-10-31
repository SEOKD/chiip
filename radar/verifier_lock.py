"""평가기 잠금 (ADR-013 H4, 마스터 승인 2026-10-31) — 채점표·측정기가 조용히 바뀌지 않았는지 해시로 확인

변조를 드러낼 뿐 막지는 않는다. 다시 잠그는 일은 마스터 승인을 받은 세션에서만 사유와 함께 한다.
사용: py radar/verifier_lock.py --check
      py radar/verifier_lock.py --relock "사유"
"""
import csv
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "evals" / "verifier.lock"
CHANGES = ROOT / "evals" / "verifier_changes.csv"
FILES = ["evals/rules.yaml", "scripts/lab/rule_evals.py", "radar/pulse_check.py", "radar/verifier_lock.py"]


def digest(root=ROOT):
    return {f: hashlib.sha256((root / f).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for f in FILES}


def check(root=ROOT):
    """달라진 파일 목록"""
    lock = root / "evals" / "verifier.lock"
    saved = json.loads(lock.read_text(encoding="utf-8")) if lock.exists() else {}
    return [f for f, h in digest(root).items() if saved.get(f) != h]


def relock(reason):
    if not reason.strip():
        raise ValueError("사유가 없다")
    changed = check()
    LOCK.write_text(json.dumps(digest(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    new = not CHANGES.exists()
    with CHANGES.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "files", "reason"])
        w.writerow([datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d"), " ".join(changed), reason])
    return changed


def run():
    """run_hourly용 — 어긋나면 마스터에게 알린다"""
    bad = check()
    if bad:
        import notify
        notify.send(f"[Chiip 평가기 잠금] 승인 기록 없이 바뀐 파일: {', '.join(bad)}", "SYSTEM")
        raise RuntimeError(f"평가기 변경 감지: {', '.join(bad)}")
    return 0, []


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--relock" in sys.argv:
        print("다시 잠금:", relock(sys.argv[sys.argv.index("--relock") + 1]))
        sys.exit(0)
    found = check()
    print("평가기 잠금 일치" if not found else f"어긋남: {found}")
    sys.exit(1 if found else 0)
