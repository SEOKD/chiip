"""역방향 레이더 진입점 (BUILD_PROMPT §11.11) — 수집만, 판정은 scout/triangulator

사용: py radar/reverse/run_reverse.py [edgar|dart|twse|all]
- edgar: 하루 수 회 (미국 업무 시간)   - dart: 하루 1~2회   - twse: 매일(새 달 데이터만 반영)
v0 범위(§21.7): 이 세 수집기만. 나머지 레이어는 CES 이후.
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "collectors"))

JOBS = {
    "edgar": ("edgar_fts", "src-edgar-fts"),
    "dart": ("dart_counterparty", "src-dart-counterparty"),
    "twse": ("twse_monthly", "src-twse-monthly"),
}


def main(argv):
    which = argv[0] if argv else "all"
    import importlib
    from common_rev import common
    for name, (mod, sid) in JOBS.items():
        if which not in ("all", name):
            continue
        try:
            print(name, importlib.import_module(mod).run())
        except RuntimeError as exc:
            common.record_health(sid, False, exc)
            print(f"{name}: 건너뜀 — {exc}")
        except Exception as exc:
            common.record_health(sid, False, f"{type(exc).__name__}: {exc}")
            print(f"{name}: 오류 — {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
