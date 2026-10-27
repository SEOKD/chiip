"""단위·시각 표기 경고 — BUILD_PROMPT §5.7

사용법:
    py scripts/check_units.py                # knowledge/ 와 outputs/ 전체
    py scripts/check_units.py 경로 [경로...]   # 파일 또는 폴더
경고만 출력하고 종료 코드는 항상 0 (unit-guard는 차단이 아니라 경고).
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTS = {".md", ".yaml", ".yml", ".csv", ".json", ".txt"}

RULES = [
    (re.compile(r"\b\d+(?:\.\d+)?\s?(?:gb|tb|mb|gbit)\b"),
     "소문자 단위 — 비트(Gb)인지 바이트(GB)인지 명확히"),
    (re.compile(r"\b\d+(?:\.\d+)?\s?(?:GBps|TBps|gbps)\b"),
     "비표준 표기 — 바이트는 GB/s, 비트는 Gbps"),
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?![\d:+\-Z])"),
     "시각에 시간대 없음 — +09:00(KST) 또는 원 시간대 표기"),
    (re.compile(r"^(?=.*(?:데이터센터|data ?center))(?=.*\b\d+(?:\.\d+)?\s?(?:MW|GW)\b)(?!.*(?:IT|시설|facility|critical))", re.I),
     "데이터센터 전력 — 시설 전력인지 IT 부하인지 명시"),
    (re.compile(r"^(?=.*\bwpm\b|.*웨이퍼)(?=.*(?:출하|비트))", re.I),
     "웨이퍼 투입·완제품 출하·비트 출하가 한 문장에 — 기준 분리 확인"),
    (re.compile(r"^(?=.*HBM)(?=.*(?:탑재량|용량|content))(?!.*(?:다이|스택|GPU|서버|die|stack|per))", re.I),
     "HBM 탑재량 기준(다이·스택·GPU·서버) 명시"),
]


def iter_files(paths):
    for p in paths:
        p = Path(p)
        if p.is_dir():
            yield from (f for f in p.rglob("*") if f.suffix.lower() in EXTS)
        elif p.is_file():
            yield p


def main(argv):
    targets = argv or [ROOT / "knowledge", ROOT / "outputs"]
    count = 0
    for f in iter_files(targets):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(lines, 1):
            for pattern, msg in RULES:
                if pattern.search(line):
                    count += 1
                    print(f"[경고] {f}:{n} {msg}")
    print(f"단위 경고 {count}건")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
