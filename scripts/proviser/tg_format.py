"""Proviser 일일 텔레그램 양식 관문 (마스터 지시 2026-11-19 "* Portfolio와 * Weekly 사이에 문단 띄어쓰기는 한 번만 적용하라").

점수 목록(`* 이름 x.x(±d.d)` 줄들)은 핵심 3개(Pulse·Analysis·Portfolio) 다음에 빈 줄 정확히 하나, 나머지 점수 줄 사이에는 빈 줄 없음.
글 전체에서 빈 줄이 두 줄 이상 겹치면 한 줄로 줄인다. 숫자·문장은 건드리지 않는다.
사용: py scripts/proviser/tg_format.py <tg.txt>          # 파일을 고쳐 쓰고 결과를 출력
      py scripts/proviser/tg_format.py <tg.txt> --send   # 고친 뒤 notify.send(…, 'PROVISER')
"""
import re
import sys
from pathlib import Path

CORE = ("Pulse", "Analysis", "Portfolio")
SCORE = re.compile(r"^\* \S")


def fix(text):
    lines = text.replace("\r\n", "\n").split("\n")
    idx = [i for i, l in enumerate(lines) if SCORE.match(l)]
    if idx:
        a, b = idx[0], idx[-1]
        scores = [l for l in lines[a:b + 1] if l.strip()]
        core = [l for l in scores if re.match(r"^\* (%s) (\d|신규)" % "|".join(CORE), l)]   # 'Pulse Weekend'은 핵심이 아니다
        rest = [l for l in scores if l not in core]
        block = core + ([""] if core and rest else []) + rest
        lines = lines[:a] + block + lines[b + 1:]
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return out


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    p = Path(argv[0])
    t = fix(p.read_text(encoding="utf-8"))
    p.write_text(t, encoding="utf-8", newline="\n")
    if "--send" in argv:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "radar"))
        import notify
        print("발송" if notify.send(t, "PROVISER") else "발송 실패")
    else:
        print(t)


if __name__ == "__main__":
    main(sys.argv[1:])
