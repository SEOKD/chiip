"""Proviser 일일 텔레그램 양식 관문.

마스터 지시 2026-11-19(두 번째, 예시 양식): 점수 목록(`* 이름 x.x(±d.d)`)은 빈 줄 없이 한 덩어리로 붙이고,
그 아래 본문 문단은 모두 `■`로 시작한다. 문단 사이에는 빈 줄 하나. 겹친 빈 줄은 한 줄로 줄인다. 숫자·문장은 건드리지 않는다.
(같은 날 첫 지시 "핵심 3개와 나머지 사이 빈 줄 한 번"은 이 예시 양식으로 대체됐다)
사용: py scripts/proviser/tg_format.py <tg.txt>          # 파일을 고쳐 쓰고 결과를 출력
      py scripts/proviser/tg_format.py <tg.txt> --send   # 고친 뒤 notify.send(…, 'PROVISER')
"""
import re
import sys
from pathlib import Path

SCORE = re.compile(r"^\* \S")
HEAD = re.compile(r"^\[Chiip Proviser")


def fix(text):
    lines = text.replace("\r\n", "\n").split("\n")
    idx = [i for i, l in enumerate(lines) if SCORE.match(l)]
    if idx:
        a, b = idx[0], idx[-1]
        lines = lines[:a] + [l for l in lines[a:b + 1] if l.strip()] + lines[b + 1:]
    out = []
    for l in lines:
        s = l.strip()
        if s and not SCORE.match(s) and not HEAD.match(s) and not s.startswith("■"):
            l = "■" + s
        out.append(l)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


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
