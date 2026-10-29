"""리포트 게시 — 만든 리포트를 GitHub(비공개 저장소)의 claude/reports 브랜치에 올리고 마스터 텔레그램으로 링크를 보낸다
(마스터 지시 2026-10-29 "리포트를 작성하면 내 봇으로 github 링크를 보내는 작업도 엔진에 추가해줘")

- 작업 트리·현재 브랜치·스테이징을 건드리지 않는다: 임시 인덱스로 claude/reports 브랜치 위에 파일만 얹은 커밋을 만들어 푸시한다
  (여러 세션·예약 작업이 같은 폴더를 쓰므로). main에는 올리지 않는다(CLAUDE.md: 에이전트 자동 변경은 claude/* 브랜치).
- 링크는 비공개 저장소라 마스터가 로그인한 상태에서만 열린다. GitHub는 HTML을 소스로 보여 준다 — 그래프가 그려진 화면은
  텔레그램으로 받은 파일을 열면 된다(링크는 보관·공유용).
사용: py scripts/publish_report.py <파일> [<파일> ...] --title "<제목 한 줄>" [--no-send]
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANCH = "claude/reports"


def git(*args, env=None, input_=None):
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8",
                       env=env, input=input_, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))   # 예약 작업에서 창 없이(2026-10-30)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} 실패: {r.stderr.strip()[:200]}")
    return r.stdout.strip()


def repo_web():
    url = git("remote", "get-url", "origin")
    m = re.search(r"github\.com[:/](.+?)(?:\.git)?$", url)
    if not m:
        raise RuntimeError("origin이 GitHub가 아님")
    return f"https://github.com/{m.group(1)}"


def base_commit():
    """원격 claude/reports가 있으면 그 끝, 없으면 main 끝 위에 쌓는다"""
    try:
        git("fetch", "-q", "origin", f"{BRANCH}:refs/remotes/origin/{BRANCH}")
        return git("rev-parse", f"refs/remotes/origin/{BRANCH}")
    except RuntimeError:
        return git("rev-parse", "refs/remotes/origin/main")


def publish(paths, title):
    rels = []
    for p in paths:
        ap = (ROOT / p).resolve() if not Path(p).is_absolute() else Path(p).resolve()
        rel = ap.relative_to(ROOT).as_posix()
        if rel.startswith(("D:", "../")) or "local-only" in rel:
            raise RuntimeError(f"게시 금지 경로: {rel}")
        rels.append((ap, rel))
    title = title.replace("치입", "Chiip")   # GitHub 보고 표기(마스터 지시 2026-10-29)
    parent = base_commit()
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(tmp) / "index"))
        git("read-tree", parent, env=env)
        for ap, rel in rels:
            blob = git("hash-object", "-w", str(ap))
            git("update-index", "--add", "--cacheinfo", f"100644,{blob},{rel}", env=env)
        tree = git("write-tree", env=env)
    if tree == git("rev-parse", f"{parent}^{{tree}}"):
        commit = parent   # 같은 내용이면 새 커밋 없이 링크만
    else:
        msg = f"리포트 게시: {title}\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
        commit = git("commit-tree", tree, "-p", parent, input_=msg)
        git("push", "-q", "origin", f"{commit}:refs/heads/{BRANCH}")
    web = repo_web()
    return [f"{web}/blob/{commit[:12]}/{rel}" for _, rel in rels], commit


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--title", required=True)
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--caption", default="", help="링크 위에 붙일 요약(파일 경로 또는 글) — 텔레그램은 GitHub 링크만(마스터 지시 2026-10-30)")
    a = ap.parse_args(argv)
    links, commit = publish(a.files, a.title)
    print(f"[게시] {BRANCH} {commit[:12]}")
    for l in links:
        print(l)
    if not a.no_send:
        sys.path.insert(0, str(ROOT / "radar"))
        import notify
        cap = Path(a.caption).read_text(encoding="utf-8").strip() if a.caption and Path(a.caption).exists() else a.caption.strip()
        text = (cap + "\n\n" if cap else f"[Chiip Report] {a.title}\n") + "\n".join(links) + "\n(비공개 저장소 — 로그인 필요)"
        print("텔레그램:", notify.send(text, "REPORT"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
