"""펄스 양식 건별 점검 (마스터 지시 2026-10-31 Chiip Laboratory) — 결정론

docs/tasks/chiip-pulse.md 3단계의 판단 건 양식 중 코드로 잴 수 있는 것을 건마다 잰다.
evals/rules.yaml이 측정에 쓰고, 출처 링크(link)는 notify.send가 발송 관문으로 쓴다.
사용: py radar/pulse_check.py <tg 파일>
"""
import re
import sys
from pathlib import Path

HEAD = re.compile(r"^\S*\s*[①-⑳]\s.*｜")
CUT = re.compile(r"^(─{3,}|간단히$|그 외 새 건 없음)")
LINK = re.compile(r"https?://|출처 미확인")
NUM = re.compile(r"(?<![A-Za-z\d.,/-])\d[\d,.]*(?![\dQqHh/-])")   # 3Q·FY26·10/29는 값이 아니다
MAX_JUDGMENT, MAX_EVIDENCE, MAX_NUMBERS, MAX_LINES = 60, 55, 2, 5


def blocks(text):
    """판단 건 목록. 머리줄부터 구분선·'간단히' 앞까지"""
    out, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if HEAD.match(line):
            cur = [line]
            out.append(cur)
        elif CUT.match(line):
            cur = None
        elif cur is not None and line:
            cur.append(line)
    return out


def check(text):
    """(점검 이름, 머리줄, 내용) 목록"""
    out = []
    for b in blocks(text):
        head, rest = b[0], b[1:]
        if not LINK.search("\n".join(b)):
            out.append(("link", head, "출처 링크 없음"))
        if not rest or rest[0].startswith(("**", "·", "인사이트")):
            out.append(("company", head, "사업 1줄 없음"))
        evidence = [x[1:].strip() for x in rest if x.startswith("·")]
        out += [("judgment", head, x) for x in (y.strip("*") for y in rest if y.startswith("**")) if len(x) > MAX_JUDGMENT]
        out += [("evidence", head, x) for x in evidence if len(x) > MAX_EVIDENCE]
        out += [("numbers", head, x) for x in evidence if len(NUM.findall(x)) > MAX_NUMBERS]
        if len(evidence) > MAX_LINES:
            out.append(("count", head, f"근거 {len(evidence)}줄"))
    return out


def unlinked(text):
    """발송 관문용 — 출처 링크가 없는 판단 건의 머리줄"""
    return [h for name, h, _ in check(text) if name == "link"]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    rows = check(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for name, head, detail in rows:
        print(f"{name}: {head[:40]} — {detail[:50]}")
    sys.exit(1 if any(r[0] == "link" for r in rows) else 0)
