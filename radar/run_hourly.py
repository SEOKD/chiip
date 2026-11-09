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
sys.path.insert(0, str(HERE.parent / "scripts" / "discovery"))   # asia_screen(대만 월매출 급증, 2026-11-09)
from pollers import common  # noqa: E402

JOBS = [  # (job id, module, interval_min)
    ("src-fedreg", "fedreg", 60),
    ("src-edgar-fts", "edgar_fts", 120),
    ("src-twse-monthly", "twse_monthly", 1440),
    ("src-tw-financials", "pollers.tw_financials", 360),  # 대만 공시 분기 손익·재무상태(TWSE·TPEx OpenAPI, 모델 없음, 2026-11-07 마스터 지시)
    ("src-press-wire", "pollers.press_wire", 30),  # PR Newswire·Business Wire (저녁 브리프 '글로벌 공식 발표')
    ("src-spac-watch", "pollers.spac_watch", 30),  # SPAC 감지·생애 단계 장부(SIC 6770 EDGAR 검색 + S2~S4 후속 추적, 2026-11-04 마스터 지시 1단계)
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
    ("src-dticker", "dticker", 30),  # 딘스티커 공개 미리보기 읽기 전용 — 알림 없음
    ("jp-ir-audit", "pollers.jp_ir_audit", 10080),  # 일본 IR 자료실·전문·Q&A 커버리지 표, 주 1회(전 사이트를 읽어 약 10분, 모델 없음, 마스터 지시 2026-11-01)
    ("jp-tv-docs", "jp_tv_docs", 60),  # 일본 어닝콜 전사 확인 대상 갱신(TradingView 호출은 펄스 회차의 모델이 3종목씩, 2026-11-02 마스터 지시)
    ("self-heal", "self_heal", 60),  # 수집 채널 이상 탐지·재시도(모델 없음, 2026-11-02 마스터 지시)
    ("notion-library", "notion_library", 30),  # 노션 첨부 색인·본문 추출, NOTION_TOKEN 경로(모델 없음, 2026-11-04 마스터 지시)
    ("trade-ppi", "trade_ppi", 1440),
    ("trade-hs", "trade_hs", 1440),  # HS 시계열·급등 품목(모델 없음, 2026-11-02 마스터 지시)  # 6개국 무역·PPI 세부 항목(모델 없음, 2026-11-02 마스터 지시)
    ("korea-watch", "korea_watch", 60),  # 한국 기업 미국 활동·해외 M&A 단서(모델 없음, 2026-11-03 마스터 지시) — 360→60분, 일치 항목은 inbox로(2026-11-04)
    ("patent-watch", "patent_watch", 180),  # 한국 전자기업 특허 등록·분쟁(기자 페이지·미 ITC·언론 색인 + 키 대기 원천, 모델 없음, 2026-11-08 마스터 지시)
    ("cftc", "cftc", 360),  # CFTC 투자자 포지션(COT) 주간 — 새 주가 나오면 계산·극단이면 inbox(모델 없음, 2026-11-09 마스터 지시)
    ("ir-audio", "ir_audio", 60),  # IR 설명회 음성 자체 전사(로컬 faster-whisper, D등급) — 한 회차 1건(마스터 승인 2026-11-09)
    ("asia-revenue", "asia_screen", 180),  # 대만 전 종목 월매출 급증(전자 업종, 감시 밖 회사 포함) → inbox src-tw-revenue-surge(모델 없음, 2026-11-09 마스터 지시 대만·중국 발굴 보완)
    ("eia", "eia", 1440),  # EIA 전력 통계(RTO 수요·주별 상업용 판매·계획 발전 설비) — 키 대기면 건너뜀(마스터 승인 2026-11-09, TODO 21-41)
    ("overseas-sites", "overseas_sites", 360),  # 한국 전자기업 해외 거점 정부 자료·수출입 거울(모델 없음, 2026-11-08 마스터 지시)
    ("site-imagery", "site_imagery", 10080),  # 생산시설 위성 영상·변화 측정, 주 1회(모델 없음, 2026-11-03 마스터 지시)
    ("exclusive-leads", "exclusive_leads", 360),  # 노션 Exclusive Source 단서의 공개 근거 후보(모델 없음, 판정은 펄스 회차, 2026-11-02 마스터 지시)
    ("proviser-channels", "channel_scout", 60),  # Proviser 회차의 채널 탐색 누락을 장부에 적는다(모델 없음, 마스터 지시 2026-11-01)
    ("verifier-lock", "verifier_lock", 1440),  # 평가기 잠금 일일 확인(ADR-013 H4)
    ("pulse-heartbeat", "pulse_trigger", 30),  # 펄스 문턱이 멈췄으면 모델 없이 알린다(ADR-013 H2)
    ("src-literature", "literature", 360),  # 논문·실무 리서치(판단은 예약 작업 chiip-model-lab)
    ("src-sec-xbrl", "markets.sec_xbrl", 10080),  # 미국 상장·ADR 재무 이력(주 1회)
    ("src-prices-free", "markets.prices_free", 720),  # 무료 시세(TWSE·TPEx, KRX·Finnhub는 키 입력 후)
    ("src-sec-bulk", "sec_bulk", 43200),  # SEC 일괄 재무 → 기저율 표본(월 1회, SEC_USER_AGENT 필요 — 없으면 건너뜀)
    ("src-regime", "regime", 1440),
    ("src-sec-earnings-all", "pollers.sec_earnings_all", 60),  # 전체 미국 상장사 실적(8-K 2.02) → AI·전력 업종이면 알파 산정 대기열(Investing 캘린더 대체)
    ("src-alpha-watch", "alpha_watch", 60),  # 핵심 루프: P0·P1 알림·알파 진입·실적일 → 알파 ≥5면 v2 3요인 텔레그램(동인 없으면 대기열)  # 밸류에이션 v2 시장 체제(FRED 국채·스프레드·환율) — 하루 1회
    ("src-earnings-calendar", "markets.earnings_calendar", 30),
    ("src-attention", "attention", 1440),
    ("src-consumer-attention", "consumer_attention", 1440),  # Chiip Consumer 수요 관심도(IP·브랜드 위키 조회·스팀·애플 순위·브랜드 뉴스, 2026-10-30 마스터 지시)  # Chiip Ten-bagger Discovery 투자자 관심도(하루 1회, 2026-10-29 마스터 지시)
    ("src-p2-digest", "p2_digest", 30),  # P2·막힌 P0/P1 하루 1통 요약 — 모듈이 08~10시 첫 실행 때만 발송(2026-10-29 마스터 지시)  # AI 밸류체인 어닝 일정 — 수집 6시간마다, 07~09시 알파 5점 이상만 텔레그램
]


def main(argv):
    common.stay_awake()
    force = "--force" in argv
    new_radar = False
    for jid, mod, every in JOBS:
        if not force and not common.is_due(jid, every):
            continue
        try:
            res = importlib.import_module(mod).run()
            print(jid, res)
            if jid in ("src-fedreg", "src-legistar", "korea-watch") and res[1]:  # 레이더 inbox에 새 항목을 넣는 작업
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
