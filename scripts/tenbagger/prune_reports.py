"""같은 종목의 옛 Analysis 리포트를 GitHub에서 지운다 (마스터 지시 2026-11-04 "11월 4일에 Erock 보고서를 쓰고 12월 4일에 한 번 더 썼다면
11월 4일분의 기록은 Github에서 삭제하라" — 노션은 이미 덮어쓴다, publish_tenbagger.existing_notion)

대상: outputs/tenbagger/reports/ 의 <날짜>_<티커>[.확장자|_꼬리], charts/<날짜>_<티커>_n.svg, delivery/<날짜>_<티커>.json 중 새 리포트보다 날짜가 이른 것.
  티커가 정확히 같을 때만(PWR과 PWRX는 다르다). 장부(delivery.csv·log.csv·notion_log.csv 등)와 다른 폴더는 건드리지 않는다.
경로: ① claude/reports 브랜치 — publish_tenbagger.prepare가 drop()으로 받아 같은 게시 커밋에서 뺀다
     ② 작업 트리(main) — remove()가 지우고 radar/state/pruned.txt에 적는다. 코드 가드 훅은 이 목록에 있는 파일만 삭제를 허용한다.
사용: py scripts/tenbagger/prune_reports.py <새 리포트 json 또는 stem> [--dry]
"""
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REP = "outputs/tenbagger/reports"
MANIFEST = ROOT / "radar" / "state" / "pruned.txt"
KST = timezone(timedelta(hours=9))
NAME = re.compile(r"^(?P<date>\d{8})_(?P<ticker>[A-Za-z0-9.\-]+?)(?=$|_|\.(?:html|json|md|txt|svg)$)")


def parse(stem):
    m = NAME.match(Path(stem).name)
    if not m:
        raise SystemExit(f"리포트 이름이 아님: {stem}")
    return m["date"], m["ticker"].upper()


def older(paths, stem):
    """paths(저장소 기준 경로) 가운데 같은 종목·더 이른 날짜의 리포트 파일"""
    date, ticker = parse(Path(stem).stem)
    out = []
    for p in paths:
        if not p.startswith(REP + "/"):
            continue
        sub = p[len(REP) + 1:]
        if "/" in sub and not sub.startswith(("charts/", "delivery/")):
            continue
        m = NAME.match(sub.split("/")[-1])
        if m and m["ticker"].upper() == ticker and m["date"] < date:
            out.append(p)
    return sorted(out)


def git(*args):
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, encoding="utf-8")
    return r.stdout if r.returncode == 0 else ""


def drop(stem, ref="refs/remotes/origin/claude/reports"):
    """claude/reports 브랜치에서 뺄 옛 파일"""
    git("fetch", "-q", "origin", "claude/reports:refs/remotes/origin/claude/reports")
    return older(git("ls-tree", "-r", "--name-only", ref, REP).split("\n"), stem)


def remove(stem, dry=False):
    """작업 트리에서 옛 파일을 지우고 허용 목록에 적는다"""
    here = [p.relative_to(ROOT).as_posix() for p in (ROOT / REP).rglob("*") if p.is_file()]
    gone = older(here, stem)
    if gone and not dry:
        MANIFEST.parent.mkdir(parents=True, exist_ok=True)
        with MANIFEST.open("a", encoding="utf-8") as f:   # 지우기 전에 적는다 — 훅의 복구가 이 목록을 본다
            f.writelines(f"{datetime.now(KST).isoformat(timespec='seconds')}\t{p}\n" for p in gone)
        for p in gone:
            (ROOT / p).unlink(missing_ok=True)
    return gone


def allowed():
    """코드 가드가 삭제를 허용하는 경로(이 스크립트가 지운 것만)"""
    if not MANIFEST.exists():
        return set()
    return {ln.split("\t", 1)[1].strip() for ln in MANIFEST.read_text(encoding="utf-8").splitlines() if "\t" in ln}


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if not argv:
        raise SystemExit(__doc__)
    dry = "--dry" in argv
    stem = Path(argv[0]).stem
    print("작업 트리:", remove(stem, dry) or "없음")
    print("claude/reports:", drop(stem) or "없음")


if __name__ == "__main__":
    main(sys.argv[1:])
