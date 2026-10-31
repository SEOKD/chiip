"""Chiip Proviser 글 점검 (마스터 지시 2026-10-31 "에이전트 결과물이 맞춤법과 오타가 없는지도 점검하고, 가독성을 떨어뜨리는 요인이 있다면 이를 개선하도록 해라")

결정론으로 잡을 수 있는 것만 걸러 모델 점검의 바닥을 만든다 — 맞춤법 판단 자체는 모델이 한다(docs/tasks/chiip-proviser.md 6-4).
  오타 흔적: 같은 낱말 연속 · 문장부호 중복 · 깨진 글자 · 조사 앞 공백
  가독성: 120자 넘는 문장 · 300자 넘는 문단 · 한 문장 숫자 8개 초과
사용: py scripts/proviser/text_lint.py <파일>...
"""
import re
import sys
from pathlib import Path

LONG_SENTENCE, LONG_PARA, MANY_NUMBERS = 120, 300, 8
URL = re.compile(r"https?://\S+")
SPLIT = re.compile(r"(?<=[다요음임함됨.!?])[.!?]?\s+")
TYPO = (("같은 낱말 연속", re.compile(r"(?<![\w·])([가-힣A-Za-z]{2,})\s+\1(?![\w가-힣])")),
        ("문장부호 중복", re.compile(r"[,，]{2,}|(?<!\.)\.\.(?!\.)|[?!]{3,}")),
        ("깨진 글자", re.compile(r"[�﻿]|ï¿½")),
        ("조사 앞 공백", re.compile(r"[가-힣A-Za-z0-9%)] (?:은|는|이|가|을|를|에서|으로)(?= )")))


def lint(text):
    out = []
    for no, raw in enumerate(text.splitlines(), 1):
        line = URL.sub("", raw).strip()
        if not line or line.startswith(("|", "#")):
            continue
        for name, pat in TYPO:
            m = pat.search(line)
            if m:
                out.append((no, name, m.group(0)[:30]))
        if len(line) > LONG_PARA:
            out.append((no, f"긴 문단 {len(line)}자", line[:30]))
        for s in SPLIT.split(line):
            if len(s) > LONG_SENTENCE:
                out.append((no, f"긴 문장 {len(s)}자", s[:30]))
            n = len(re.findall(r"\d[\d,.]*", s))
            if n > MANY_NUMBERS:
                out.append((no, f"한 문장 숫자 {n}개", s[:30]))
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    total = 0
    for f in argv:
        rows = lint(Path(f).read_text(encoding="utf-8", errors="replace"))
        total += len(rows)
        print(f"{f}: {len(rows)}건")
        for no, name, ctx in rows[:40]:
            print(f"  {no}행 {name}: {ctx}")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
