"""봉인 정보·비밀키 유출 검사 — BUILD_PROMPT §3.1, §9 (pre-commit에서 자동 실행)

사용법:
    py scripts/scan_sealed.py            # 저장소 전체
    py scripts/scan_sealed.py --staged   # 커밋 대기 파일만 (pre-commit용)
    py scripts/scan_sealed.py 파일...     # 지정 파일

- 금칙어는 D:\\local-only\\sealed\\denylist.txt (환경변수 CHIIP_LOCAL_ONLY로 경로 변경 가능)
- 금칙어·비밀값 자체는 절대 출력하지 않는다. "금칙어 #번호", "비밀키 패턴(종류)"만 표시.
걸리면 종료 코드 1.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_ONLY = Path(os.environ.get("CHIIP_LOCAL_ONLY", r"D:\local-only"))
DENYLIST = LOCAL_ONLY / "sealed" / "denylist.txt"
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv"}
TEXT_EXTS = {".md", ".yaml", ".yml", ".csv", ".json", ".jsonl", ".txt", ".py", ".ps1", ".sh", ".toml", ".ini", ""}

SECRET_PATTERNS = [
    ("텔레그램 봇 토큰", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("GitHub 토큰", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Anthropic 키", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("개인 키", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("키=값 형태 비밀값", re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|client[_-]?secret|password|crtfc_key)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}")),
]
# local-only 원문을 그대로 옮긴 흔적
# (자리표시자 `<FI-id>.md` 같은 설명용 경로는 제외)
LOCAL_PATH_RE = re.compile(r"(?i)local-only[\\/](?:sealed|embargo|licensed|secrets)[\\/](?:[^\s<>{}*`'\"\\/]+[\\/])*[^\s<>{}*`'\"\\/]+\.(?:txt|md|pdf|docx|csv)")


def load_denylist():
    if not DENYLIST.exists():
        return []
    terms = []
    for line in DENYLIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms.append(line.lower())
    return terms


def staged_files():
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return [ROOT / p for p in out.stdout.splitlines() if p.strip()]


def all_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


def display(path):
    try:
        return path.resolve().relative_to(ROOT)
    except ValueError:
        return path


def scan(path, terms):
    hits = []
    if path.suffix.lower() not in TEXT_EXTS or not path.is_file():
        return hits
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return hits
    is_self = path.resolve() == Path(__file__).resolve()
    for n, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        for i, term in enumerate(terms, 1):
            if term in low:
                hits.append(f"{display(path)}:{n} 금칙어 #{i}")
        if is_self:
            continue
        for kind, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                hits.append(f"{display(path)}:{n} 비밀키 패턴({kind})")
        if LOCAL_PATH_RE.search(line):
            hits.append(f"{display(path)}:{n} local-only 원문 파일 경로 언급 — 내용 복제 여부 확인")
    return hits


def main(argv):
    terms = load_denylist()
    if not DENYLIST.exists():
        print(f"[안내] 금칙어 파일 없음: {DENYLIST} — 비밀키 패턴만 검사합니다.")
    if "--staged" in argv:
        files = staged_files()
    elif argv:
        files = [Path(a).resolve() for a in argv]
    else:
        files = list(all_files())
    hits = []
    for f in files:
        hits.extend(scan(f, terms))
    for h in hits:
        print(f"[차단] {h}")
    print(f"검사 {len(files)}개 파일, 문제 {len(hits)}건")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
