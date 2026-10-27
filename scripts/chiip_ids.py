"""다음 ID 발급 — docs/schema.md ID 규칙

사용법:
    py scripts/chiip_ids.py claim [YYYYMMDD]    -> C-20261027-001
    py scripts/chiip_ids.py source [YYYYMMDD]   -> S-20261027-001
    py scripts/chiip_ids.py signal [YYYYMMDD]   -> SIG-20261027-0001
    py scripts/chiip_ids.py card [YYYYMMDD] [HHMM] -> R-20261027-1543-001
    py scripts/chiip_ids.py field               -> FI-0001
    py scripts/chiip_ids.py event [YYYYMMDD]    -> EV-20261027-001
날짜를 생략하면 오늘(KST).
"""
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))


def today():
    return datetime.now(KST).strftime("%Y%m%d")


def max_seq(pattern, texts):
    best = 0
    for text in texts:
        for m in re.finditer(pattern, text):
            best = max(best, int(m.group(1)))
    return best


def names_under(*dirs):
    for d in dirs:
        p = ROOT / d
        if p.exists():
            for f in p.rglob("*"):
                yield f.name


def file_text(*files):
    for f in files:
        p = ROOT / f
        if p.exists():
            yield p.read_text(encoding="utf-8")


def next_id(kind, day=None, hhmm=None):
    day = day or today()
    if kind == "claim":
        n = max_seq(rf"C-{day}-(\d{{3}})", names_under("knowledge/claims"))
        return f"C-{day}-{n + 1:03d}"
    if kind == "source":
        n = max_seq(rf"S-{day}-(\d{{3}})", file_text("sources/index.yaml"))
        return f"S-{day}-{n + 1:03d}"
    if kind == "signal":
        n = max_seq(rf"SIG-{day}-(\d{{4}})", names_under("radar/reverse/signals"))
        return f"SIG-{day}-{n + 1:04d}"
    if kind == "card":
        hhmm = hhmm or datetime.now(KST).strftime("%H%M")
        n = max_seq(rf"R-{day}-\d{{4}}-(\d{{3}})", names_under("radar/cards"))
        return f"R-{day}-{hhmm}-{n + 1:03d}"
    if kind == "event":
        n = max_seq(rf"EV-{day}-(\d{{3}})", names_under("radar/events"))
        return f"EV-{day}-{n + 1:03d}"
    if kind == "field":
        n = max_seq(r"FI-(\d{4})", file_text("knowledge/field_intel_index.csv"))
        return f"FI-{n + 1:04d}"
    raise SystemExit(f"알 수 없는 종류: {kind}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    print(next_id(sys.argv[1], *(sys.argv[2:4])))
