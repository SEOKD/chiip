"""코드 삭제 가드 훅 (2026-11-02 마스터 지시 "짜놓은 코드를 에이전트가 스스로 삭제하지 않도록")

pre  (PreToolUse, Bash·PowerShell·Write·Edit):
  delete-guard   코드 파일·git 추적 파일(2026-11-04 확대, 예외는 prune_reports.py의 옛 리포트)을 지우거나 옮기거나 비우는 명령, 코드 삭제를 담은 git commit
  git-guard      git clean·reset --hard·stash·강제 푸시·--no-verify처럼 코드를 날리거나 검사를 건너뛰는 명령
  gut-guard      Write·Edit로 코드 파일을 비우는 저장, 설정에서 훅을 빼는 저장
  → 모두 승인 창 없이 거부(deny). 에이전트는 삭제를 시도하지 않고, 필요한 삭제는 마스터가 직접 한다(2026-11-02 마스터 지시 "삭제 시도 하지마라").
  shrink-guard   Write·Edit로 코드를 크게 줄이는 저장 → 정리 작업일 수 있어 마스터 승인 창(ask), 승인할 사람이 없는 실행은 거부.
post (PostToolUse·PostToolUseFailure, Bash·PowerShell):
  restore-guard  명령 전후로 새로 사라진 추적 코드 파일을 HEAD 내용으로 복구. 스크립트·변수로 지운 경우까지 잡는다.
                 명령 전에 이미 없던 파일(마스터가 직접 지운 파일)은 건드리지 않는다.

훅 자체의 오류는 작업을 멈추지 않는다(exit 0, 기록은 radar/state/code_guard.log).
"""
import glob
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parents[2]).resolve()
KST = timezone(timedelta(hours=9))

CODE_SUFFIX = {".py", ".ps1", ".sh", ".bat", ".cmd", ".js", ".ts", ".css"}
CODE_DIRS = (".claude/", ".githooks/", ".github/", "scripts/", "tests/", "evals/", "config/", "extension/", "docs/tasks/", "docs/channels/")
CODE_FILES = {"CLAUDE.md", "requirements.txt", ".gitignore", ".gitattributes"}
NOT_CODE = ("outputs/", ".claude/worktrees/")
NOT_CODE_PARTS = {"__pycache__", ".venv", "node_modules", ".git"}
HOOKS = ("chiip_guard.py", "code_guard.py")
GUT_MIN_LINES = 20   # 이보다 짧은 파일은 절반 규칙을 쓰지 않는다
GUT_MAX_DROP = 100   # 한 번에 줄어드는 줄 수 상한

SHELL_TOOLS = ("Bash", "PowerShell")
FILE_TOOLS = ("Write", "Edit", "MultiEdit")
ASK_FREE_MODES = ("bypassPermissions", "dontAsk")   # 승인 창이 없는 모드
KEEP_SNAP_SEC = 86400

REMOVE = {"rm", "rmdir", "rd", "del", "erase", "unlink", "shred", "truncate", "remove-item", "ri", "clear-content", "clc", "set-content", "out-file", "tee", "tee-object"}
MOVE = {"mv", "move", "ren", "rename", "move-item", "mi", "rename-item", "rni"}
WRAP = {"sudo", "command", "env", "time", "nohup"}
SHELLS = {"bash", "sh", "zsh", "cmd", "powershell", "pwsh"}
CD = {"cd", "set-location", "sl", "pushd"}

TOKEN = re.compile(r"\"[^\"]*\"|'[^']*'|[;|&\n]+|[^\s;|&]+")
REDIRECT = re.compile(r"(?<![>0-9&=-])>(?![>=])\s*(\"[^\"]*\"|'[^']*'|[^\s;|&)]+)")
INLINE = re.compile(r"(?:os\.(?:remove|unlink|rmdir|rename|replace)|shutil\.(?:rmtree|move)|\[(?:System\.)?IO\.(?:File|Directory)\]::(?:Delete|Move))\(\s*(?:Path\()?\s*r?[\"']([^\"']+)"
                    r"|Path\(\s*r?[\"']([^\"']+)[\"']\s*\)\.(?:unlink|rmdir|write_text|write_bytes)\(")


def state_dir():
    d = ROOT / "radar" / "state" / "code_guard"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log(line):
    try:
        with (state_dir().parent / "code_guard.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now(KST).isoformat(timespec='seconds')} {line}\n")
    except OSError:
        pass   # 기록 실패가 판정을 막으면 안 된다


def protected(r):
    if r.startswith(NOT_CODE) or set(r.split("/")) & NOT_CODE_PARTS:
        return False
    return r in CODE_FILES or r.startswith(CODE_DIRS) or Path(r).suffix.lower() in CODE_SUFFIX


_TRACKED = None


def tracked():
    global _TRACKED
    if _TRACKED is None:
        _TRACKED = set(git("ls-files", "-z").decode("utf-8").split("\0")) - {""}
    return _TRACKED


def pruned():
    """prune_reports.py가 지운 같은 종목 옛 리포트 — 마스터가 명령한 유일한 에이전트 삭제(2026-11-04)"""
    f = ROOT / "radar" / "state" / "pruned.txt"
    if not f.exists():
        return set()
    return {ln.split("\t", 1)[1].strip() for ln in f.read_text(encoding="utf-8").splitlines() if "\t" in ln}


def guarded(r):
    """지우면 안 되는 파일: 코드, 그리고 git이 추적하는 모든 파일(마스터 지시 2026-11-04 "명령한 것 외에 다른 소스코드나 파일을
    삭제하지 않도록"). 예외는 prune_reports.py가 적은 옛 리포트뿐"""
    if r in pruned():
        return False
    return protected(r) or r in tracked()


def unquote(t):
    return t.strip("\"'")


def full(token, cwd):
    t = re.sub(r"^/([a-zA-Z])/", r"\1:/", unquote(token))
    return os.path.join(str(cwd), os.path.expanduser(t))


def rel(path):
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except (ValueError, OSError):
        return None


def hits(token, cwd):
    """대상 토큰이 건드리는 보호 경로(파일, 또는 코드를 품은 폴더)"""
    out = []
    if not unquote(token):   # 따옴표만 남은 토큰(문자열 안의 >)은 대상이 아니다
        return out
    p = full(token, cwd)
    for name in (glob.glob(p, recursive=True) if re.search(r"[*?\[]", unquote(token)) else [p]):
        try:
            path = Path(name).resolve()
        except OSError:
            continue
        if path == ROOT or path in ROOT.parents:
            return ["."]
        r = rel(path)
        if r is None:
            continue
        if path.is_file() and guarded(r):
            out.append(r)
        elif path.is_dir():
            for base, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in NOT_CODE_PARTS]
                if any(guarded(rel(os.path.join(base, f)) or "") for f in files):
                    out.append(r)
                    break
    return out


def segments(cmd):
    seg = []
    for t in TOKEN.findall(cmd):
        if t[0] in ";|&\n":
            if seg:
                yield seg
            seg = []
        else:
            t = t if t[0] in "\"'" else t.strip("(){}")
            if t:
                seg.append(t)
    if seg:
        yield seg


def word(t):
    w = re.split(r"[\\/]", unquote(t))[-1].lower()
    return w[:-4] if w.endswith(".exe") else w


def is_flag(a):
    return a.startswith("-") or re.fullmatch(r"/[a-zA-Z]", a) is not None


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    return r.stdout if r.returncode == 0 else b""


def missing(*extra):
    """HEAD에는 있는데 지금 없는 보호 파일. 이름 바꾸기(git mv)는 삭제가 아니다."""
    names = git("diff", "HEAD", *extra, "--name-only", "--diff-filter=D", "-z").decode("utf-8").split("\0")
    return [r for r in names if r and guarded(r)]


def git_reason(seg):
    """위험한 git 명령이면 사유를 돌려준다"""
    args = [unquote(a) for a in seg[1:]]
    head = []
    while len(args) > 1 and args[0] in ("-C", "-c"):
        head += args[:2]
        args = args[2:]
    sub, rest = (args[0].lower(), args[1:]) if args else ("", [])
    flags = set(rest)
    if any("core.hookspath" in a.lower() for a in head + rest) and "--get" not in flags:
        return "git 훅 경로 변경"
    if sub == "clean" and not flags & {"-n", "--dry-run"}:
        return "git clean(추적 안 된 파일 삭제)"
    if sub == "reset" and flags & {"--hard", "--merge", "--keep"}:
        return "git reset --hard(고친 내용 버림)"
    if sub == "checkout" and flags & {"--", ".", "-f", "--force"}:
        return "git checkout으로 고친 내용 버림"
    if sub == "restore" and (not flags & {"--staged", "-S"} or flags & {"--worktree", "-W"}):
        return "git restore로 고친 내용 버림"
    if sub == "stash" and (not rest or rest[0] not in ("list", "show")):
        return "git stash(고친 내용 치움)"
    if sub == "push" and (flags & {"-f", "-d", "--delete", "--mirror", "--no-verify"} or any(a.startswith(("--force", "+")) for a in rest)):
        return "강제 푸시 또는 원격 삭제"
    if sub == "commit" and flags & {"-n", "--no-verify"}:
        return "커밋 검사 건너뛰기"
    if sub in ("filter-branch", "filter-repo") or (sub == "update-ref" and "-d" in flags) or (sub == "branch" and flags & {"-D"}):
        return "git 이력·브랜치 삭제"
    return None


def scan(cmd, cwd, depth=0):
    """명령을 읽어 (사유, 보호 경로 또는 None) 목록을 낸다"""
    found = []

    def add(reason, token):
        found.extend((reason, h) for h in hits(token, cwd))

    for m in REDIRECT.finditer(cmd):
        add("덮어쓰기", m[1])
    for m in INLINE.finditer(cmd):
        add("삭제", m[1] or m[2])
    for seg in segments(cmd):
        while seg and word(seg[0]) in WRAP:
            seg = seg[1:]
        if not seg:
            continue
        name, args = word(seg[0]), [a for a in seg[1:] if not is_flag(a)]
        if name in CD and args:
            cwd = full(args[0], cwd)
        elif name in REMOVE:
            for a in args:
                add("삭제", a)
        elif name in MOVE:
            for a in args[:-1] or args:
                add("이동", a)
        elif name == "find" and ("-delete" in seg or re.search(r"-exec(dir)?\s+\S*\brm\b", " ".join(seg))):
            for a in seg[1:]:
                if is_flag(a):
                    break
                add("삭제", a)
        elif name in SHELLS and depth < 2:
            for i, a in enumerate(seg):
                if a.lower() in ("-c", "-command", "/c", "/k"):
                    found += scan(" ".join(unquote(x) for x in seg[i + 1:]), cwd, depth + 1)
                    break
        elif name == "git":
            found += scan_git(seg, cwd)
    return found


def scan_git(seg, cwd):
    args = [unquote(a) for a in seg[1:]]
    if len(args) > 1 and args[0] == "-C":
        cwd, args = full(args[1], cwd), args[2:]
    sub = args[0].lower() if args else ""
    found = []
    reason = git_reason(seg)
    if reason:
        found.append((reason, None))
    if sub == "rm":
        for a in args[1:]:
            if not is_flag(a):
                found.extend(("삭제", h) for h in hits(a, cwd))
    elif sub == "commit":
        every = any(a == "--all" or re.fullmatch(r"-[a-zA-Z]*a[a-zA-Z]*", a) for a in args[1:])
        found.extend(("코드 삭제가 담긴 커밋", r) for r in missing(*(() if every else ("--cached",))))
    return found


def decide(reason, event, soft=False):
    """삭제는 거부한다. soft는 줄이기만 하는 저장이라 사람이 있으면 승인 창을 띄운다."""
    unattended = event.get("permission_mode") in ASK_FREE_MODES or os.environ.get("CLAUDE_CODE_SESSION_ATTENDED") == "0"
    verdict = "ask" if soft and not unattended else "deny"
    log(f"{verdict} {event.get('tool_name')} {reason}")
    tail = "마스터 승인이 있어야 합니다." if verdict == "ask" else "에이전트는 코드를 지우지 않습니다. 다시 시도하지 말고 필요하면 마스터에게 알리세요."
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": verdict,
                                             "permissionDecisionReason": f"[치입 코드 가드] {reason} — {tail}"}}))


def pre_shell(event):
    ti = event.get("tool_input") or {}
    found = scan(ti.get("command", ""), event.get("cwd") or ROOT)
    if found:
        decide(" / ".join(dict.fromkeys(f"{why}: {h}" if h else why for why, h in found[:6])), event)
    elif event.get("tool_use_id"):
        (state_dir() / f"{event['tool_use_id']}.json").write_text(json.dumps({"before": missing()}), encoding="utf-8")


def after_edit(tool, ti, old):
    if tool == "Write":
        return ti.get("content", "")
    edits = ti.get("edits") if tool == "MultiEdit" else [ti]
    for e in edits or []:
        old = old.replace(e.get("old_string", ""), e.get("new_string", ""), -1 if e.get("replace_all") else 1)
    return old


def pre_file(event):
    tool, ti = event.get("tool_name"), event.get("tool_input") or {}
    r = rel(full(ti.get("file_path", ""), event.get("cwd") or ROOT))
    if r is None or not protected(r):
        return
    p = ROOT / r
    old = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
    new = after_edit(tool, ti, old)
    if r.startswith(".claude/settings") and ("disableAllHooks" in new or (r == ".claude/settings.json" and not all(h in new for h in HOOKS))):
        decide(f"설정에서 훅을 빼는 저장: {r}", event)
        return
    a, b = len(old.splitlines()), len(new.splitlines())
    if a and not new.strip():
        decide(f"코드 파일 비우기: {r}", event)
    elif (a >= GUT_MIN_LINES and b < a / 2) or a - b >= GUT_MAX_DROP:
        decide(f"코드 대량 축소: {r} {a}줄 → {b}줄", event, soft=True)


def restore(r):
    blob = subprocess.run(["git", "cat-file", "--filters", f"HEAD:{r}"], cwd=ROOT, capture_output=True)
    if blob.returncode:
        return False
    p = ROOT / r
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(blob.stdout)
    return True


def post(event):
    f = state_dir() / f"{event.get('tool_use_id')}.json"
    if not f.exists():
        return
    snap = json.loads(f.read_text(encoding="utf-8"))
    f.unlink()
    cutoff = time.time() - KEEP_SNAP_SEC
    for old in state_dir().glob("*.json"):   # 거부된 명령의 스냅숏은 post가 오지 않는다
        if old.stat().st_mtime < cutoff:
            old.unlink(missing_ok=True)
    back = [r for r in missing() if r not in snap["before"] and restore(r)]
    if back:
        log(f"restore {event.get('tool_name')} {' '.join(back[:20])}")
        print(json.dumps({"systemMessage": f"[치입 코드 가드] 지워진 코드 {len(back)}건을 복구했습니다.",
                          "hookSpecificOutput": {"hookEventName": event.get("hook_event_name", "PostToolUse"),
                                                 "additionalContext": "[치입 코드 가드] 승인 없이 지워진 코드를 마지막 커밋 내용으로 복구했습니다: " + ", ".join(back[:20])}}))


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "pre"
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except ValueError:
        return 0
    tool = event.get("tool_name", "")
    if mode == "post":
        if tool in SHELL_TOOLS:
            post(event)
    elif tool in SHELL_TOOLS:
        pre_shell(event)
    elif tool in FILE_TOOLS:
        pre_file(event)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:   # 가드 오류로 모든 작업이 멈추면 안 된다
        log(f"error {type(e).__name__}: {e}")
        sys.exit(0)
