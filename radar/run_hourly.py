"""저빈도 수집 진입점 — 역방향 레이더 v0 + 미국 관보 (작업 스케줄러 30분마다)

원천별 간격(분): 관보 60, EDGAR 전문 검색 120, 대만 월매출 1440.
DART 타사·공시유보는 2026-10-28 마스터 결정으로 제외(국내 공시는 마스터가 직접 접함).
새 레이더 항목(관보)이 생기면 run_triage를 호출한다. 역방향 후보는 scout가 판정한다.
사용: py radar/run_hourly.py [--force]
"""
import importlib
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "reverse" / "collectors"))
sys.path.insert(0, str(HERE / "usgov" / "federal"))
sys.path.insert(0, str(HERE / "usgov" / "adapters"))
sys.path.insert(0, str(HERE / "talent" / "collectors"))
from pollers import common  # noqa: E402

JOBS = [  # (job id, module, interval_min)
    ("src-fedreg", "fedreg", 60),
    ("src-edgar-fts", "edgar_fts", 120),
    ("src-twse-monthly", "twse_monthly", 1440),
    ("src-press-wire", "pollers.press_wire", 30),  # PR Newswire·Business Wire (저녁 브리프 '글로벌 공식 발표')
    # 5단계 v1
    ("src-communities", "communities", 60),
    ("src-foreign-press", "foreign_press", 120),
    ("src-openalex", "openalex", 10080),
    ("src-page-diff", "page_diff", 1440),
    ("src-job-boards", "jobs_boards", 1440),
    ("src-legistar", "legistar", 1440),
    # 6단계 v2
    ("src-kernel-lore", "kernel_watch", 1440),
    ("src-pci-ids", "pci_ids", 10080),
    ("src-usaspending", "usaspending", 10080),
]


def main(argv):
    force = "--force" in argv
    new_radar = False
    for jid, mod, every in JOBS:
        if not force and not common.is_due(jid, every):
            continue
        try:
            res = importlib.import_module(mod).run()
            print(jid, res)
            if jid == "src-fedreg" and res[1]:
                new_radar = True
        except RuntimeError as exc:
            common.record_health(jid, False, exc)
            print(f"{jid}: 건너뜀 — {exc}")
        except Exception as exc:
            common.record_health(jid, False, f"{type(exc).__name__}: {exc}")
            print(f"{jid}: 오류 — {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=1)
        finally:
            common.mark_run(jid)
    if new_radar:
        import run_triage
        run_triage.main([])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
