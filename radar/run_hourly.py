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
sys.path.insert(0, str(HERE.parent / "scripts" / "valuation" / "v2"))
from pollers import common  # noqa: E402

JOBS = [  # (job id, module, interval_min)
    ("src-fedreg", "fedreg", 60),
    ("src-edgar-fts", "edgar_fts", 120),
    ("src-twse-monthly", "twse_monthly", 1440),
    ("src-press-wire", "pollers.press_wire", 30),  # PR Newswire·Business Wire (저녁 브리프 '글로벌 공식 발표')
    ("src-weekly-movers", "markets.weekly_movers", 30),  # EODHD 주간 상승률 — 모듈이 토 06~09시·주 1회만 실제 실행
    ("src-valuation", "markets.valuation_data", 30),  # 밸류에이션 수집·계산 — 모듈이 05~06시·15:45~17시에만 실제 실행
    # 5단계 v1
    ("src-communities", "communities", 60),
    ("src-foreign-press", "foreign_press", 120),
    ("src-openalex", "openalex", 10080),
    ("src-page-diff", "page_diff", 1440),
    ("src-job-boards", "jobs_boards", 1440),
    ("src-legistar", "legistar", 240),  # 지방 안건 — 실시간 보고 대상(§21.12)
    # 6단계 v2
    ("src-kernel-lore", "kernel_watch", 1440),
    ("src-pci-ids", "pci_ids", 10080),
    ("src-usaspending", "usaspending", 10080),
    # 부가가치 엔진(§21.14) — 모델 고도화 재료. 레이더 판정·알림과 무관
    ("src-literature", "literature", 360),  # 논문·실무 리서치(판단은 예약 작업 chiip-model-lab)
    ("src-sec-xbrl", "markets.sec_xbrl", 10080),  # 미국 상장·ADR 재무 이력(주 1회)
    ("src-prices-free", "markets.prices_free", 720),  # 무료 시세(TWSE·TPEx, KRX·Finnhub는 키 입력 후)
    ("src-sec-bulk", "sec_bulk", 43200),  # SEC 일괄 재무 → 기저율 표본(월 1회, SEC_USER_AGENT 필요 — 없으면 건너뜀)
    ("src-regime", "regime", 1440),
    ("src-alpha-watch", "alpha_watch", 60),  # 핵심 루프: P0·P1 알림·알파 진입·실적일 → 알파 ≥5면 v2 3요인 텔레그램(동인 없으면 대기열)  # 밸류에이션 v2 시장 체제(FRED 국채·스프레드·환율) — 하루 1회
    ("src-earnings-calendar", "markets.earnings_calendar", 30),  # AI 밸류체인 어닝 일정 — 수집 6시간마다, 07~09시 알파 5점 이상만 텔레그램
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
            if jid in ("src-fedreg", "src-legistar") and res[1]:  # 레이더 inbox에 새 항목을 넣는 작업
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
