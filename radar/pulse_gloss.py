"""Pulse 용어 풀이 (마스터 지시 2026-10-31 "Pulse에서도 전문 용어를 풀어 설명하라. 특히 기술명, 세그먼트명, 제품명, 정책 용어, 프로젝트 명 등을
풀어 설명하라. 금융 용어는 풀어 설명하지 않아도 된다")

config/pulse_glossary.yaml의 말을 한 통에서 처음 나오는 곳에 '용어(풀이)'로 넣는다 — notify.send가 레벨 PULSE 발송 직전에 부른다.
사전에 없는 말은 모델이 글에 직접 풀어 쓴다. 발송 전 확인:
    py radar/pulse_gloss.py --check <텔레그램 파일>   # 사전에 없고 풀이도 없는 영문 약자 후보(금융 용어·종목코드 제외)
"""
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GROUPS = ("technology", "segment", "product", "policy", "project")
URL = re.compile(r"(https?://[^\s)]+)")
ACRONYM = re.compile(r"(?<![A-Za-z0-9/.\-(])[A-Z][A-Z0-9&+\-]{1,}(?![A-Za-z0-9])(?![(（])")
_cache = {}


def glossary():
    if "d" not in _cache:
        d = yaml.safe_load((ROOT / "config" / "pulse_glossary.yaml").read_text(encoding="utf-8")) or {}
        _cache["d"] = {t: w for g in GROUPS for t, w in (d.get(g) or {}).items()}
        _cache["skip"] = {str(x).upper() for x in d.get("skip") or []}
        names = sorted(_cache["d"], key=len, reverse=True)
        _cache["pat"] = re.compile(r"(?<![A-Za-z0-9/.\-])(?:" + "|".join(re.escape(x) for x in names) + r")(?![A-Za-z0-9/\-])")
    return _cache["d"]


def apply(text):
    """처음 나온 용어 뒤에 (풀이). 바로 뒤에 괄호가 있으면 이미 풀이된 것으로 본다. 주소와 [이름](주소)의 주소는 건드리지 않는다"""
    terms, seen = glossary(), set()

    def one(m):
        w = m.group(0)
        if w in seen:
            return w
        seen.add(w)
        return w if m.string[m.end():m.end() + 1] in ("(", "（") else f"{w}({terms[w]})"
    return "".join(part if URL.fullmatch(part) else _cache["pat"].sub(one, part) for part in URL.split(text or ""))


def unknown(text):
    """사전에 없고 바로 뒤 풀이도 없는 영문 약자 후보 — 금융 용어·종목코드(괄호 안)는 뺀다"""
    terms = glossary()
    body = "".join(p for p in URL.split(text or "") if not URL.fullmatch(p))
    return sorted({m.group(0) for m in ACRONYM.finditer(body) if m.group(0) not in terms and m.group(0).upper() not in _cache["skip"]})


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        left = unknown(Path(sys.argv[2]).read_text(encoding="utf-8"))
        print("풀이 후보: " + (" · ".join(left) if left else "없음"))
        sys.exit(0)
    print(__doc__)
    sys.exit(1)
