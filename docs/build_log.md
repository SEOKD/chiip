# 구축 로그

> 대화가 길어져 요약되더라도 이어서 작업할 수 있도록 단계별 진행 상황을 남긴다.

## 마스터 지시 (2026-10-27 밤)
- 2~6단계 연속 진행, 게이트 생략. 권한 허용·폴더 생성 등 승인 절차는 모두 재가함.
- 단, 안전 규칙상 금지된 일(비밀번호·키 직접 입력, 계정 생성, 공개 게시 자동화)은 하지 않고 `docs/TODO_MASTER.md`에 남긴다.

## 공식 문서 확인 결과 (2026-10-27, code.claude.com)
- 스킬: `.claude/skills/<name>/SKILL.md`, 첫 줄 `---` 프론트매터(`name`, `description` 권장, `allowed-tools`, `model`, `context: fork`, `agent`, `disable-model-invocation`, `paths`). 본문 500줄 이내, 상세는 같은 폴더 보조 파일. `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}` 치환.
- 서브에이전트: `.claude/agents/<name>.md`, 필수 `name`·`description`, `tools`(허용 목록)·`disallowedTools`·`model`(`haiku|sonnet|opus|fable|inherit|전체 ID`)·`maxTurns`·`skills`(사전 로드)·`permissionMode`. 본문이 시스템 프롬프트.
- 훅: `.claude/settings.json`의 `hooks.PreToolUse[].matcher: "Write|Edit"` → `type: command`. stdin JSON에 `tool_name`, `tool_input.file_path`, Write는 `content`, Edit는 `new_string`. **exit 2 = 차단**(stderr가 Claude에 전달). Windows는 Git Bash가 있으면 셸 형식을 Git Bash로 실행.
- 헤드리스: `claude -p "<prompt>" --output-format json [--json-schema '<schema>'] --allowedTools "Read,Write" --permission-mode dontAsk|acceptEdits --permission-prompts none`. 구독 로그인은 `--bare`가 아닐 때 사용. `--bare`는 API 키 필요.

## 진행
| 단계 | 상태 | 비고 |
|---|---|---|
| 0 | 완료 | §21.8 |
| 1 | 완료 | 커밋 a4c1a80, 2770086 |
| 2 | 완료 | 커밋 8c3a8c8. field-intake 실전 시험은 마스터 메모 필요 |
| 3 | 완료 | 레이더 v0 가동(작업 스케줄러 chiip-radar 5분). DART·네이버·텔레그램 키, claude 로그인은 마스터 |
| 4 | 완료 | 훅 6종·에이전트 12종·분석 스킬·분야 모듈 11(draft)·역방향 v0(EDGAR·DART 타사·대만 월매출)·관보·작업 chiip-hourly |
| 5 | 완료 | claude.yml, 주간 리뷰·채점 6종, 역방향 v1 수집기 6종·스킬, 인재·미국 v1 스킬, Legistar 어댑터, 예약 작업(아침·저녁 등록 / 주간·역방향은 마스터 등록), CES 운용 문서 |
| 6 | 완료 | 투자·공개 스킬 6종(public-content는 Notion 게시 승인 필수), model_calc·propose_weights, v2 수집기(커널·PCI ID·USASpending), mirror-trade, 주가 원천 후보 문서, 오스틴 Legistar |

## 운영 시작 (2026-10-28)
- Claude CLI 로그인(Max) → 헤드리스 판정 실측 성공, 07:09 첫 자동 카드 3장
- 텔레그램 @chiip_dean_bot 연결, 07:17 시험 발송 성공. `notify.py --chat-id` 추가
- DART·네이버 수집 제외(마스터 결정, §21.6). 네이버 검색 API는 신규 신청 종료·개정 약관(AI 입력 금지)도 확인
- 아침 브리프 첫 실행이 도구 권한 대기로 멈춤 + 예약 작업 작업 폴더가 임시 폴더로 잡힌 문제 발견 → 세션을 저장소로 옮긴 뒤 4개 재등록(chiip-brief-morning·chiip-brief-evening·chiip-weekly-review·chiip-reverse-scout, 작업 폴더 `C:\Users\석진\chiip`, Auto 모드). 프롬프트에서 DART 제거, PATH 보정 안내 추가
- 앱이 Git·Python 설치 전 PATH로 떠 있어 훅이 모든 저장을 막음 → PC 재부팅으로 해결(훅은 수정하지 않음)
- 저녁 브리프에 '글로벌 공식 발표' 절 추가: PR Newswire 9개 피드 + Business Wire M&A 피드(`radar/pollers/press_wire.py`). MarketScreener(약관상 재사용 금지·자동 접속 403)·GlobeNewswire(자동 접속 403)는 제외
- 초안 1차 검토: `docs/reviews/2026-10-28_draft_review.md`
- 위클리 '글로벌 증시 주간 상승률'(Dean's Ticker 형식): Koyfin(API 없음·Plus 내보내기 없음)·TIKR(다운로드 불가) 검토 후 마스터가 EODHD 자동화 선택 → `radar/markets/weekly_movers.py`(토 06~09시, run_hourly 연결). 키 입력·일본 지원 확인·채널 게시 조건은 마스터 몫
- 레이더 판정 때마다 claude 콘솔 창이 뜨던 문제(10-28 하루 47회): 작업 스케줄러는 `pyw`(창 없음)인데 `run_triage.py`가 띄우는 `claude.exe`가 새 콘솔을 열었음 → `CREATE_NO_WINDOW`로 숨김 실행
- 텔레그램 알림 매체 제한(마스터 지시): 국내 언론 기사 제외, 기사는 Reuters·Bloomberg·WSJ·The Information·Business Insider·PR Newswire·GlobeNewswire만(`config/alert_rules.yaml` telegram_filter, `notify.telegram_allowed`). 막힌 P0·P1은 브리프 대기열로. 기업 뉴스룸 보도자료·공시·정부 문서는 기사가 아니므로 유지, Business Wire 수집분은 텔레그램 제외
- 밸류에이션 시스템(ADR-008, BUILD_PROMPT §21.10): IB 5곳 공개 방법 종합 → 6층(수집·리비전·멀티플·내포 기대·내러티브·반영도). `radar/markets/valuation_data.py`(EODHD 펀더멘털·가격·수동 컨센서스, 05~06시·15:45~17시), `scripts/valuation/engine.py`(순수 파이썬 회귀·역DCF·수익률 분해·반영도 지수), 스킬 `valuation-card`, 아침·저녁 브리프 '밸류에이션 레이더' 절(예약 작업 지시문 갱신). 키·요금제 전이라 지금은 내러티브 강도만 실데이터
- 리서치·투자자 실시간 감시(§21.11, 마스터 지시): `config/research_watch.yaml` 29개 계정·매체. 공개 RSS 15개(`src-research-feeds`) 가동, X 공식 API(`src-research-x`)는 코드 완성·비용 승인 대기(사용량 과금, 월 상한). X 웹 수집은 robots.txt 전면 차단이라 안 함. 트리아지 기본 P2·텔레그램 제외·아침·저녁 브리프 '리서치·투자자 동향' 절
- 텔레그램 실시간 보고 확대(§21.12, 마스터 지시): X 글 허용, 정책·행정명령(미국 연방·주·지방, EU·회원국, 일본·대만·중국)·학회·협회 원천 10개 추가(공식 RSS 직접 + 차단된 기관은 Google News 도메인 제한), 트리아지 정책·학회 P0/P1 기준, Legistar 안건 레이더 편입
- 실시간 전환(§21.13·ADR-009, 마스터 지시): 아침·저녁 브리프 예약 작업 비활성, P1도 즉시 발송 + '⭐ 노션 기록' 버튼. 수집 관문(뉴스 7곳만·포커스 종목만), SEC EDGAR 공시·실적, 7곳×포커스 종목 검색. 포커스 점수 엔진(10점·4요소, 매일 06:40 예약 작업 chiip-focus-score, 첫 산정 41/62종목 ≥5.0). 노션 비공개 허브 '치입 인텔리전스'(인텔 아카이브·오피니언·인사이트 DB)
- 신선도 관문(마스터 지시): 10/21·22 기사가 10/28 발송된 문제(src-news7-focus의 when:1d 무시) → 공개 시각 기준 수집·발송 시한(`freshness`). 포커스 점수 텔레그램은 총점만
- 뉴스 매체 9곳(마스터 지시): CNBC·Seeking Alpha 추가. 두 곳은 robots.txt가 Claude 등 AI 수집기를 차단 → Google News 색인(제목·링크)으로만
- 부가가치 엔진 A단계(§21.14·ADR-010, 마스터 승인): CLAUDE.md 사명 절, 파라미터 등록부(35개, 기존 상수 26개 이전) + 피팅 하네스(walk-forward·축소·채택 관문), 논문 수집기(arXiv q-fin·NBER·연준·다모다란·Alpha Architect), SEC XBRL 재무 이력(39종목), 스킬 insight-review·model-lab·article-pitch·tenbagger-card, 노션 인사이트 DB 검토 속성 6개, 예약 작업 4개(인사이트 07:30·21:30, 모델 연구 14:30, 기사 소재 평일 16:40, 텐배거 토 10:30), 예측 원장 owner·origin 열
- 데이터 요금제(마스터 결정): EODHD ALL-IN-ONE 승인. 키 입력(마스터) 후 B단계
- 어닝 캘린더·알파 점수(§21.15, 마스터 지시): KIND IR일정 수집(10/28~11/18 15건), 알파 잠재력 첫 산정 17종목(5.0 이상 10), 07~09시 5점 이상만 텔레그램. 노션 Insights·Informations·Stocks 역할 고정, insight-review를 Insights 하위 페이지 기준으로 개정
- 밸류에이션 v2(§21.16, 마스터 승인): 설계안·문헌 노트, 1단계 엔진(regime·wacc·reorg·dcf·pie·baserates·montecarlo·upside·run) + 시험 13개, INNIO·Vertiv·Micron 시험 카드, SEC XBRL 계정 교체 기간 보완, 요인 분해 도구(factor_impact)
- 무료 데이터 조합(마스터 결정): EODHD 보류. TWSE·TPEx 무료 시세 수집(대만 8종목), SEC 일괄 재무 기저율 수집기(SEC_USER_AGENT 대기), KRX·Finnhub 키 대기
- 컨센서스·어닝콜 수동 입력(마스터 제안): 노션 Informations > 'Consensus · Earnings Call' DB, 요청 27건(알파 후보 10종목·v2 이관 7종목, 컨센서스 17·한국 어닝콜 10), 처리 경로를 인사이트 검토 예약 작업·earnings-delta에 연결
- 치입 크롬 확장(마스터 선택): 로컬 서버(scripts/chiip_server.py, 127.0.0.1:8765, 토큰 인증) + 확장(extension/chiip: 옆 패널·우클릭 보내기·설정), 마스터 제보는 레이더 판정 또는 ⭐ 노션 대기열, 시험 6개
- 핵심 루프·3요인(§21.17, 마스터 승인): decision.py(매수 매력·위험 예산 지표·상방)·alpha_watch.py(매시간 감지 → v2 → 텔레그램), 등록부 prm-v2-dec-* 7개, 시험 8개. 동인 작성 예약 작업은 안전 분류기 거부 → 초안만
- GEV 누락 수정·데이터센터 전력 55종목 레이더 편입(§21.18): 엔티티·수집 관문·SEC 공시(CIK 회사명 보조)·inbox 직접 감지·알파 산정 대기열, GEV 알파 5.5 → v2 3요인 발송
- 알파 레이더 자동화(§21.19): 전체 미국 상장사 실적 스캐너(EDGAR 8-K 2.02·SIC 선별·초소형 제외) → 알파 산정 대기열 → 예약 작업이 산정·감시 목록 추가·동인·텔레그램 요약. 10/27 수동 레이더 24종목 산정, 13종목 신규 5점 이상
- 내러티브 프리미엄(§21.20, 마스터 지시): 원천 약관·robots 점검 → 자동 수집 10곳(Substack 10개 공개 RSS·Hacker News·Google News 색인의 SA·Fool·Benzinga·MarketBeat·Barron's·IBD·Investopedia·TipRanks·Zacks 제목·IB 커버리지 변화 제목) + 모델 단계(easyconomics 콜 질문·노션 IB 요지). 레딧·VIC·StockTwits·X·SA/Fool 직접 접속 제외. `radar/narrative_sources.py`(제목 언급·재게재 필터), 스킬 narrative-premium, 첫 분석 UCTT(태동·gap+1)·TTMI(컨센서스·gap+1)·VICR(확산·과밀·gap−1/upside+1), 등록부 섹터 내러티브 3개 추가, 3요인 메시지 '내러티브' 줄, 시험 7개. 예약 작업 개정은 분류기 거부 → 마스터 '개정 승인' 후 반영
- 노션 올림 즉시 처리(§21.16, 마스터 지시): notion_watch(토큰 시 5분)·chiip-notion-watch(매시간)·notion-intake 스킬·notion_state·notion_write. 첫 처리: Informations 법안 추적표 → 중간선거 후 수혜 후보 보고서·텔레그램 발송
- 30분 펄스(§21.21, 마스터 지시): `radar/pulse.py`(결정론 관문 — inbox의 원본만[논문·보도자료·공시·정부, 기사 제외] + arXiv cs.ET·physics.app-ph 직접 + 감시 목록 밖 AI·전력 업종 8-K 1.01·7.01·8.01, 유형별 상한, 후보 티커, 회차 잠금, valuation-queue 실행 창 회피), 예약 작업 chiip-pulse(`*/30`, 자동 모드, ① [기사 원본] ② 텐배거 발굴 → 알파 산정 ≤8 → [알파 레이더]), 시험 5개. Nature 계열은 robots.txt가 Claude 차단 → 제외
- 알파 점수 SemiAnalysis 렌즈(§21.17, 마스터 지시): 7원리 + 크라우딩, 42종목 규칙 보정(29행), 5.0 이상 23종목
- 밤사이 미실행(2026-10-29): PC가 22:55~07:28 절전(S3) → 예약 작업·수집기 정지(reporter·ten-bagger 지연, pulse 16회 건너뜀). 마스터 승인으로 작업 스케줄러 chiip-radar(5분)·chiip-hourly(30분)에 '절전 중 깨우기', 수집 중 절전 방지(`common.stay_awake`, 프로세스 종료 시 해제). 윈도우 전원 설정은 그대로(마스터 몫), 배터리일 때는 깨우기 타이머 비활성(기존 설정)
- Chiip proviser(§21.22, 마스터 지시 '6개만 남겼다, 더 만들지 마라'): 남은 6개 기능의 추론을 다른 방식(역추적·기저율·사전 부검·경쟁 가설·숫자 재계산·결정 가치 + 기능별 반대 렌즈)으로 재평가하는 틀 `docs/proviser/README.md`, 첫 평가(pulse 5.5·Weekly 6.0·reporter 6.5·ten-bagger 7.5·Model Lab 8.0·Notion 8.5 — 모두 9 미만) → 기능별 10점 근거·보강 지시 24개를 `docs/proviser/<taskId>.md`에, 6개 작업지시서 끝에 '프로바이저 보강' 절 삽입. 매일 재평가 예약 작업은 05:30 안이 분류기 거부 → 마스터 지시로 매일 22:00 등록
- 프로바이저 '매일 향상'(마스터 지시 '역량을 매일 향상, 전일보다 떨어지면 반드시 끌어올려라, 익스포넨셜'): 요인 3층(사고 구조·추론 구조·체계) 원장, 회귀 탐지 → 5 Whys → 복구 지시 R-, 9점 이상도 매일 지렛대 지시 1개, 졸업 지시 → 상시 원칙(누적), 교차 전파 X-, 7일 이동 평균·정체 시 접근 전환. 기준선 원장 기록, 프로바이저 작업지시서 개정
- ten-bagger 30분 주기(마스터 지시): 매시 15·45분(pulse 00·30분과 엇갈림), 관문 = radar/state/tenbagger_last.txt 이후 새 병목 신호(카드·페어·내러티브·pulse 원본·5점 이상 판단) 없으면 즉시 종료, 전 종목 재산정은 토요일 첫 회차·월간 점검은 첫 토요일 첫 회차만, 신규 후보 하루 2개 상한. 프로바이저 D-04 갱신
- ten-bagger easyconomics 데이터(마스터 지시): 후보·알파 대상 종목마다 재무·실적 지표·컨센서스·어닝콜·수출(trade_nowcast), 하루 한 번 매크로 컴포짓·유동성 모니터·시장 포지셔닝(radar/state/tenbagger_market_<날짜>.md 재사용). 1차 자료와 다르면 1차 우선, 실패는 미확인, 원문 통째 저장 금지
- pulse 개정(마스터 지시): 미보도 원문만(영어권·국내 언론 검색으로 보도 여부 확인, 보도됐으면 제외, 없으면 '없음'), 8-K 첨부·보도자료 속 숨은 이름까지 끝까지 훑기, 한 통에 미보도 원문 + 알파 레이더 함께, '작성' 대기열 적재 중단
- Chiip Portfolio(§21.23, 마스터 지시): `config/portfolio.yaml`(EROC·INIO·CCXI·MRVL·PWR — SEC cik로 실체 확인, CCXI = Agility Robotics 합병 스팩·환매 마감 10/29 17:00 ET·주총 11/2), 결정론 관문 `radar/portfolio.py`(SEC 새 제출·Google News 색인 보도자료·9개 매체·IB 커버리지·커뮤니티 제목·ApeWisdom 레딧 언급·위키 조회·HN·일정 알림, 커버리지 기록·전일 대비, 일정 추가), 레이더 관문·어닝 캘린더 보유 종목 포함, 시험 6개, 첫 실행 6건(INIO 3Q 실적 8-K·CCXI 일정·MRVL 레딧 언급 18회/전일 1회). 예약 작업 chiip-portfolio(매시 35분) 마스터 승인 후 등록·프로바이저 예약 작업 7개 대상으로 개정
- 누락 교정(§21.24, 마스터 지시): Broadcom–Anthropic 630억 달러·앤트로픽 IPO·Meta 증자/엔비디아 투자·MRVL–Lumentum이 T0 중심 판정으로 P2 → 읽히지 않는 브리프 대기열. 판정 상향 규칙(`radar/promote.py` 6종·24시간 서명)·스킬 radar-triage 'AI 밸류체인·보유 종목' 절, P2 하루 1통(`radar/p2_digest.py`, 08~10시), 펄스 ③ AI 파이낸싱(`config/financing_watch.yaml` 40개 발행사 SEC 자금 조달 서류 + 자금 조달 제목, 미보도 규칙 제외, 직전 대비 비교) — 예약 작업 chiip-pulse 개정, 포트폴리오 첫 회차 뉴스 기준선 폐지·IB 제목 필터, 시험 8개

## 마스터 할 일
`docs/TODO_MASTER.md`
