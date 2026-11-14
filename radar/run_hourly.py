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
    ("src-press-wire", "pollers.press_wire", 60),  # PR Newswire·Business Wire — 주 수집은 run_poll src-press-fast(5분, 2026-11-11), 여기는 예비
    ("src-spac-watch", "pollers.spac_watch", 30),  # SPAC 감지·생애 단계 장부(SIC 6770 EDGAR 검색 + S2~S4 후속 추적, 2026-11-04 마스터 지시 1단계)
    ("src-weekly-movers", "markets.weekly_movers", 30),  # EODHD 주간 상승률 — 모듈이 토 06~09시·주 1회만 실제 실행
    ("src-valuation", "markets.valuation_data", 30),  # 밸류에이션 수집·계산 — 모듈이 05~06시·15:45~17시에만 실제 실행
    # 5단계 v1
    ("src-communities", "communities", 60),
    ("src-foreign-press", "foreign_press", 120),
    ("src-openalex", "openalex", 10080),
    ("src-page-diff", "page_diff", 1440),
    ("kr-foreign-hiring", "pollers.kr_foreign_hiring", 60),  # 해외 반도체 기업 한국 채용(마이크론·인텔·엔비디아·KLA·어플라이드 Workday + 사람인 키 대기, 2026-11-11 마스터 지시)
    ("src-job-boards", "jobs_boards", 360),  # 협업사 공개 채용(Greenhouse·Lever·Ashby 25곳) — 삼성·SK하이닉스 파트너십 과제 문구, 1440→360분(2026-11-11 마스터 지시)
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
    ("ppi-release", "ppi_release", 10),  # BLS PPI 발표일(calendar.csv)에만 발표 10분 뒤~3시간 BLS만 묻고 새 달·개정을 반영, inbox 한 건(모델 없음, 마스터 지시 2026-11-13)
    ("cpi-release", "cpi_release", 10),  # BLS CPI 발표일에만 발표 10분 뒤~3시간(모델 없음, 마스터 지시 2026-11-13)
    ("kr-exports", "kr_exports", 30),
    ("options-implied", "options_implied", 240),  # 실적일 14일 안 감시 종목 옵션 ATM 스트래들(Cboe 지연 시세, 마스터 승인 2026-11-14, ADR-033)  # 산업부 월간 수출입 동향(매월 1~3일 09~20시) 반도체·컴퓨터 — 못 읽으면 공백만(모델 없음, 2026-11-13)
    ("trade-hs", "trade_hs", 1440),  # HS 시계열·급등 품목(모델 없음, 2026-11-02 마스터 지시)  # 6개국 무역·PPI 세부 항목(모델 없음, 2026-11-02 마스터 지시)
    ("korea-watch", "usgov.korea_watch", 60),  # 한국 기업 미국 활동·해외 M&A 단서(모델 없음, 2026-11-03 마스터 지시) — 360→60분, 일치 항목은 inbox로(2026-11-04)
    ("patent-watch", "patent_watch", 180),  # 한국 전자기업 특허 등록·분쟁(기자 페이지·미 ITC·언론 색인 + 키 대기 원천, 모델 없음, 2026-11-08 마스터 지시)
    ("cftc", "cftc", 360),  # CFTC 투자자 포지션(COT) 주간 — 새 주가 나오면 계산·극단이면 inbox(모델 없음, 2026-11-09 마스터 지시)
    ("ir-audio", "ir_audio", 60),  # IR 설명회 음성 자체 전사(로컬 faster-whisper, D등급) — 한 회차 1건(마스터 승인 2026-11-09)
    ("asia-revenue", "asia_screen", 180),  # 대만 전 종목 월매출 급증(전자 업종, 감시 밖 회사 포함) → inbox src-tw-revenue-surge(모델 없음, 2026-11-09 마스터 지시 대만·중국 발굴 보완)
    ("eia", "eia", 1440),  # EIA 전력 통계(RTO 수요·주별 상업용 판매·계획 발전 설비) — 키 대기면 건너뜀(마스터 승인 2026-11-09, TODO 21-41)
    ("gpu-rental", "gpu_rental", 360),  # GPU 렌털료(Nebius·CoreWeave·Lambda 가격표, Silicon Data 공개 지수, TrendForce 가격 보도자료) — 변화만 inbox(모델 없음, 2026-11-10 마스터 지시)
    ("semianalysis-jobs", "semianalysis_jobs", 60),  # SemiAnalysis 공식 채용 페이지 — Memory Analyst(한국) 새 공고만 inbox(모델 없음, 2026-11-11 마스터 지시)
    ("tickertrends", "tickertrends", 1440),  # TickerTrends 관심 가속(유료 API·내부용, 키 대기 시 건너뜀, 2026-11-12 마스터 지시)
    ("edinet", "edinet", 60),  # EDINET 법정 공시 목록(감시 일본 회사, 본문 미수집) — 키 대기 시 건너뜀(2026-11-12 마스터 지시)
    ("alphavantage", "alphavantage", 1440),  # Alpha Vantage 실적 일정(무료 하루 25회 중 1회, 키 대기 시 건너뜀, 2026-11-11 마스터 지시)
    ("ir-press-find", "pollers.ir_press", 30),  # 감시 미국 종목 IR 보도자료 RSS 찾기(회차당 8곳, 30일마다 재확인) — 읽기는 run_poll src-ir-press 10분(2026-11-11 마스터 지시)
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
    ("src-sec-earnings-all", "pollers.sec_earnings_all", 30),  # 60→30분(2026-11-11 실시간 점검)  # 전체 미국 상장사 실적(8-K 2.02) → AI·전력 업종이면 알파 산정 대기열(Investing 캘린더 대체)
    ("src-13f-market", "thirteenf_market", 60),  # 13F 시즌(마감 D−2~D+40)에만 SEC 정보표 원문 전수 수집, 회차당 15분 예산·모델 없음(2026-11-14 마스터 지시)
    ("src-fulltext-retry", "fulltext", 60),  # 원문 열람 실패(SEC 403 등) 재시도 — 1시간 간격 최대 6회, 모델 없음(2026-11-13 마스터 지시)
    ("src-alpha-watch", "alpha_watch", 60),  # 핵심 루프: P0·P1 알림·알파 진입·실적일 → 알파 ≥5면 v2 3요인 텔레그램(동인 없으면 대기열)  # 밸류에이션 v2 시장 체제(FRED 국채·스프레드·환율) — 하루 1회
    ("src-earnings-calendar", "markets.earnings_calendar", 30),
    ("src-attention", "attention", 1440),
    ("src-consumer-macro", "consumer_macro", 360),   # 한국 외 소비 통계(미 FRED·일 가계조사·JNTO·유럽 Eurostat·영 ONS) — 새 달에 문턱 넘는 업종만 지표 발표(2026-11-14 마스터 지시)
    ("src-consumer-discovery", "consumer_discovery", 1440),   # 한국 외 소비 트렌드 발굴(애플·스팀 순위, 위키 상위, 급상승 검색 → 상장사, 2026-11-14)
    ("src-consumer-attention", "consumer_attention", 1440),  # Chiip Consumer 수요 관심도(IP·브랜드 위키 조회·스팀·애플 순위·브랜드 뉴스, 2026-10-30 마스터 지시)  # Chiip Ten-bagger Discovery 투자자 관심도(하루 1회, 2026-10-29 마스터 지시)
    ("src-p2-digest", "p2_digest", 30),  # P2·막힌 P0/P1 하루 1통 요약 — 모듈이 08~10시 첫 실행 때만 발송(2026-10-29 마스터 지시)  # AI 밸류체인 어닝 일정 — 수집 6시간마다, 07~09시 알파 5점 이상만 텔레그램
]


# 회차 시간 예산(2026-11-11 실시간 점검): Windows 작업 chiip-hourly는 30분 한도에 강제 종료된다(결과 0x41306). 작업을 목록 순서대로
# 한 프로세스에서 돌리다 앞쪽이 느리면 끝쪽이 굶었다 — src-attention·src-consumer-attention·src-p2-digest가 10~11일 멈췄다.
# run_poll과 같게 ① 밀린 비율(경과 ÷ 주기) 큰 작업부터 ② 작업마다 별도 프로세스 + 시간 한도 ③ 예산을 넘기면 새 작업을 시작하지 않는다.
BUDGET_MIN = 24
JOB_TIMEOUT_MIN = 10
RADAR_JOBS = ("src-fedreg", "src-legistar", "korea-watch")  # 레이더 inbox에 새 항목을 넣는 작업


def overdue(jid, every):
    """경과 ÷ 주기 — 한 번도 안 돈 작업은 가장 먼저"""
    last = common.load_state("last_run").get(jid)
    if not last:
        return 1e9
    from datetime import datetime
    return (common.now_kst() - datetime.fromisoformat(last)).total_seconds() / 60 / max(every, 1)


def run_job(jid, mod):
    """작업 하나 — 새 레이더 항목이 생겼으면 True"""
    try:
        res = importlib.import_module(mod).run()
        print(jid, res)
        return jid in RADAR_JOBS and bool(res[1])
    except RuntimeError as exc:
        common.record_health(jid, False, exc)
        print(f"{jid}: 건너뜀 — {exc}")
    except Exception as exc:
        common.record_health(jid, False, f"{type(exc).__name__}: {exc}")
        print(f"{jid}: 오류 — {type(exc).__name__}: {exc}")
        traceback.print_exc(limit=1)
    finally:
        common.mark_run(jid)
    return False


def run_child(jid, timeout_s):
    """작업 하나를 별도 프로세스로 — 멈춰도 그 작업만 끊긴다"""
    import os
    import subprocess
    try:
        r = subprocess.run([sys.executable, str(Path(__file__)), "--child", jid], capture_output=True, timeout=timeout_s,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"}, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        common.record_health(jid, False, f"시간 초과 {timeout_s / 60:.0f}분 — 다음 회차에 다시(run_hourly 작업별 한도)")
        common.mark_run(jid)
        print(f"{jid}: 시간 초과({timeout_s / 60:.0f}분)")
        return False
    out = r.stdout.decode("utf-8", "replace").rstrip().splitlines()
    for line in out[:-1]:
        print(line)
    return bool(out) and out[-1] == "NEW_RADAR"


def main(argv):
    if "--child" in argv:
        jid = argv[argv.index("--child") + 1]
        mod = next(m for j, m, _ in JOBS if j == jid)
        print("NEW_RADAR" if run_job(jid, mod) else "DONE")
        return 0
    common.stay_awake()
    force = "--force" in argv
    import time
    t0 = time.monotonic()
    due = [(j, m, e) for j, m, e in JOBS if force or common.is_due(j, e)]
    due.sort(key=lambda x: -overdue(x[0], x[2]))
    new_radar, left = False, []
    for jid, mod, every in due:
        spent = (time.monotonic() - t0) / 60
        if spent >= BUDGET_MIN:
            left.append(jid)
            continue
        new_radar |= run_child(jid, min(JOB_TIMEOUT_MIN, BUDGET_MIN + 4 - spent) * 60)
    if left:
        print(f"시간 예산 {BUDGET_MIN}분 소진 — 다음 회차로: {', '.join(left)}")
    if new_radar:
        import run_triage
        run_triage.main([])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
