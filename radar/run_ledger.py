"""실행 장부 (ADR-013 H1, 마스터 승인 2026-10-31) — 어떤 지시문 버전이 어떤 산출물을 만들었는지 잇는 추가 전용 기록

발송·관문·발행을 한 줄씩 남긴다. 본문은 저장하지 않고 해시와 글자 수만 둔다. 장부 실패가 발송을 막으면 안 되므로 예외를 삼킨다.
저장: radar/state/runs/YYYYMM.jsonl (git 제외 — 5분마다 쌓여 커밋 대상이 아니다)
사용: py radar/run_ledger.py --report [--days 7]
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))
ENABLED = "unittest" not in sys.modules   # 테스트 발송이 장부를 더럽히지 않게 한다
LEVEL_TASK = {"PULSE": "chiip-pulse", "PORTFOLIO": "chiip-portfolio", "REPORT": "chiip-tenbagger-report", "NOTION": "chiip-notion-watch"}
INSTRUCTIONS = {
    "chiip-pulse": ["CLAUDE.md", "docs/channels/pulse.md", "docs/tasks/chiip-pulse.md", "docs/proviser/chiip-pulse.md"],
    "chiip-portfolio": ["CLAUDE.md", "docs/channels/portfolio.md", "docs/tasks/chiip-portfolio.md", "docs/proviser/chiip-portfolio.md"],
    "chiip-tenbagger-report": ["CLAUDE.md", "docs/channels/tenbagger.md", "docs/tasks/chiip-tenbagger-report.md", "docs/proviser/chiip-tenbagger.md"],
    "chiip-notion-watch": ["CLAUDE.md", "docs/channels/notion.md", ".claude/skills/notion-intake/SKILL.md", "docs/proviser/chiip-notion-watch.md"],
}
TG = {"chiip-pulse": "outputs/article/sources/*_tg.txt", "chiip-portfolio": "outputs/invest/portfolio/*_tg.txt"}


def text_sha(text):
    return hashlib.sha256(text.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()[:16]


def git_commit(root=ROOT):
    """HEAD 커밋 앞 10자리. 프로세스를 띄우지 않고 파일로 읽는다"""
    head = (root / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    if not head.startswith("ref: "):
        return head[:10]
    ref = head[5:]
    loose = root / ".git" / ref
    if loose.exists():
        return loose.read_text(encoding="utf-8").strip()[:10]
    m = re.search(rf"^(\w+) {re.escape(ref)}$", (root / ".git" / "packed-refs").read_text(encoding="utf-8"), re.M)
    return m.group(1)[:10] if m else None


def instructions_hash(task, root=ROOT):
    files = INSTRUCTIONS.get(task)
    if not files:
        return None
    return text_sha("\n".join((root / f).read_text(encoding="utf-8") for f in files if (root / f).exists()))


def record(kind, task, root=ROOT, **fields):
    if not ENABLED:
        return
    try:
        now = datetime.now(KST)
        row = {"ts": now.isoformat(timespec="seconds"), "kind": kind, "task": task, "commit": git_commit(root), "instructions": instructions_hash(task, root), **fields}
        d = root / "radar" / "state" / "runs"
        d.mkdir(parents=True, exist_ok=True)
        with (d / f"{now:%Y%m}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[장부] 기록 실패 {type(exc).__name__}", file=sys.stderr)


def send_row(text, level, ok):
    task = LEVEL_TASK.get(level, level)
    gates = None
    if level == "PULSE":
        import pulse_check
        gates = dict(Counter(name for name, _, _ in pulse_check.check(text)))
    record("send", task, level=level, ok=bool(ok), text_sha=text_sha(text), chars=len(text), gates=gates)


def rows(days=7, root=ROOT):
    start = (datetime.now(KST) - timedelta(days=days)).isoformat()
    out = []
    for f in sorted((root / "radar" / "state" / "runs").glob("*.jsonl")):
        for line in f.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["ts"] >= start:
                out.append(r)
    return out


def report(days=7, root=ROOT):
    """연결률 = 장부 시작 뒤 쓴 텔레그램 파일 중 장부의 발송 해시와 맞는 비율 · 빈 회차율 = 관문이 끝낸 회차 비율"""
    rs = rows(days, root)
    if not rs:
        return {"rows": 0}
    first = datetime.fromisoformat(rs[0]["ts"]).timestamp()
    sent = {r.get("text_sha") for r in rs if r["kind"] == "send"}
    tg = [p for g in TG.values() for p in root.glob(g) if p.stat().st_mtime >= first]
    linked = sum(text_sha(p.read_text(encoding="utf-8", errors="replace")) in sent for p in tg)
    gates = [r for r in rs if r["kind"] == "gate"]
    return {"rows": len(rs), "kinds": dict(Counter(r["kind"] for r in rs)),
            "versioned": sum(bool(r.get("commit")) for r in rs) / len(rs),
            "tg_files": len(tg), "tg_linked": linked,
            "empty_gate_rate": sum(r.get("outcome") == "종료" for r in gates) / len(gates) if gates else None}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    print(json.dumps(report(ap.parse_args().days), ensure_ascii=False, indent=1))
