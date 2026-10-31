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
- 엔진 점검·개수(§21.25, 마스터 지시 '중대장은 실망했다'): Google News 쿼리 절반 포화로 기사 약 3분의 2 누락 발견 → 포화 분할 재질의·6시간 창·3시간 쓸어 담기, 보유 종목 사건 결정론 상향(큰 사건 P0·종목×사건 종류 묶음), 점검 기록 docs/audit/20261029_engine_audit.md, MRVL–Lumentum 플래시 늦은 보고 발송
- 펄스 10분·숏 리포트·신규 상장(§21.26, 마스터 지시): 펄스 `*/10`·잠금 9분, 숏 운용사 32곳 × AI 밸류체인 감지(config/short_watch.yaml)·보유 종목 숏 리포트 P0, 펄스 ④ 숏 리포트 절(주장별 1차 검증·손익분기 밸류), EDGAR 424B4·S-1 신규 상장 편입, CBRS 감시 목록 추가·Culper 리포트 검증 늦은 보고 발송
- 엔진 점검 2차(마스터 지시): 원천 주기 설정 존중(뉴스·SEC 60분→15분), 포커스 관문 폐지 → 감시 목록 196종목 전체, 잡음·중복 P1 하향, 텔레그램 긴 메시지 분할, 기능 간 중복 발송 대조 지시, claude/engine-20261029 브랜치 푸시
- 인사이트 판단 틀·일본 정보망(§21.27, 마스터 지시): CIF 7단계 문서·문헌 기저율 11종·계산기, 펄스 ⑤ 속보 판단(레이더 P0·P1을 CIF로)·모든 건 인사이트 점수, 일본 45개사 적시공시 미러·일본 매체 10분 수집·일본 사건 P1, 영문 이름 단어 경계 매칭 등 오탐 3종 교정, 이비덴 판단 늦은 보고 발송
- 텐배거 일일 리포트(§21.28, 마스터 지시): 매일 23:00 종목 1개 HTML 리포트(선정기·렌더러·차트 4종·텔레그램 파일 발송), 첫 리포트 CBRS 발송, 시험 3개
- 밸류에이션 기법 점검·데이터 묶음(§21.29, 마스터 지시): 맥킨지·IB 기법 16종 점검표, easyconomics datapack → build_drivers → v2 → v2_to_report(민감도 격자·상대가치 회귀·MC 분포 추가), CBRS 재평가(WACC 11.5%·DCF 기본 0.23배 vs 배수 1.1배·시장 내포 5년 CAGR 178%) 재발송, 예약 작업 chiip-tenbagger-report 개정
- 보고 표기 Chiip(마스터 지시): 텔레그램 발송 직전 '치입'→'Chiip' 일괄 변환(notify.brand), 리포트 HTML·GitHub 게시 제목·P2 요약 머리말, CBRS 리포트 재게시
- 즉시 포착 점검·양식(§21.30, 마스터 지시): 4.75→7.75/10 — 숏 운용사 원문 19곳·Bloomberg·BI 직접 RSS(5분), 숏 규칙(짧은 이름+대상), 규칙 빠른 길(모델 판정 전 발송), 회귀 시험 6개, 실시간 알림 한 줄 양식(종목｜기사｜시간, 등급 코드 삭제), 펄스 문단 양식·예약 작업이 지시서 파일을 읽도록 개정
- 밸류에이션 전 과정 점검(§21.31, 마스터 지시): CBRS 원자료 재호출·대조 — 가이던스 누락·톤 오기·TTM 연환산·투하자본 근사·희석 출처·동종 기준 오표기·기준 혼재 발견, 데이터 묶음 재작성·datapack_check 13개(5.0→10.0), 이익률 앵커·SBC 차감·미래 지분가치 이자 보정, 리포트 표기 개정, CBRS 기본 0.23→0.28배 재게시
- 일본 IR 질의응답·멀티플·실적 양식(§21.32, 마스터 지시): jp_ir_qa 수집기(45개사, pdftotext)·펄스 🎙 분석, multiples.py(동종 레인지·펀더멘털 내재·할인 분해·합리적 멀티플·ROIC 비례 표, 동종 영업권 SEC), CBRS 멀티플 절(동종 대비 +112% = 펀더멘털 +28% × 기업 고유 +66%, 합리적 24.6배≈0.68배), Dean's Ticker 3단 실적 양식
- Chiip Discovery·영어 표기(§21.33, 마스터 지시): 텔레그램 기능명 영어 변환, 발굴 엔진(테마 8·후보 27·관심도 추적·IB 행사 초청 신호·선별 단계 관문·커버리지·대만 원문 공시 수집과 사건 규칙·리포트 대기열 연결), 일본 IR 탐색 45개사 결과(Q&A 15곳)·Union Tool·Micronics Japan 추가, 발굴 엔진은 마스터 지시로 Chiip Ten-bagger 기능에 통합(일요일 첫 회차 발굴 전체 선별, 지시문 원본 docs/tasks/chiip-tenbagger.md 신설·예약 작업이 파일을 읽도록 개정, 별도 예약 작업 없음), Chiip Analysis 예약 시각 22:00→23:00 바로잡음
- 텐배거 리포트 어닝콜·컨센서스 절(마스터 지시 2026-10-29): scripts/tenbagger/earnings_view.py — 직전 콜 대비 변화 항목을 v2 동인 이동으로 바꿔 가치 영향(단독·확신도 가중·동시), 실적 vs 컨센서스 서프라이즈, 같은 분기 EPS·매출 리비전과 주가 = EPS 리비전 × 멀티플 분해, 동종 대비 멀티플 프리미엄(성장 조정). v2_to_report가 밸류에이션 절 앞에 자동 삽입, 시험 3건 추가. 첫 적용 INNIO(INIO) 리포트(수동 지시): 데이터 검증 10/10, 3Q 콜 정보 가치 +15.9%, 2Q 이후 EPS +4.3%·주가 −31.8% → 멀티플 −34.6%, DCF 기본 0.82배. 손으로 만든 동인은 drivers.manual_20261028.yaml로 보존하고 데이터 묶음 동인으로 교체
- X·텔레그램 관심도 집계(§21.34·ADR-011, 마스터 2026-10-29 "허용"): radar/attention.py에 X 공식 API Counts: Recent(종목당 하루 1요청 $0.005, 월 상한 1,500, 키 입력 전 건너뜀)와 텔레그램 공개 채널 웹 미리보기(t.me/s, 6채널, 7일 거슬러 읽기) 언급 글 수 집계 — 본문·작성자 미저장, 쏠림 투자자 원천에 포함. 후보 14곳 한국어 별칭(ko), 4자 이하 영문 별칭 제외. CLAUDE.md 제외 원천 문구·§21.6 개정. src-research-x(타임라인 본문)는 꺼진 채 TODO 21-3. 첫 실측 5채널 357글: 삼성전기 16·Yageo 5. 시험 7건 추가
- Proviser 개편(§21.38, 마스터 2026-10-29): 기능 7개 산출물 품질을 소수 첫째 자리로 — 루브릭(0.1 단위) + 성과 지표(놓친 사건·재발송률·브라이어·채택률·데이터 검증·검증 완료율·갱신 경과일)의 뷸만 신뢰 가중(scripts/proviser/quality.py, config/proviser.yaml). 단계적 파라미터 설계 scripts/fit/stepwise.py(데이터 확보 → 기존 피팅 → 잔차 진단 때만 논문 근거 1개 → 유지)와 harness.nested_test(Diebold-Mariano + 본페로니 누적 시도 보정), 등록부 design 절, queue.yaml → Model Lab 일요일. 예약 작업 chiip-proviser는 포인터로. 시험 tests/test_proviser.py
- Proviser 당일 텐배거 리포트 3건 점검·수정(§21.41, 마스터 2026-10-29): scripts/proviser/report_audit.py(자동 점검 13개 — 사실·과정·결론) + 모델 루브릭(사실·과정·결론·정량·반증) → 최종 0.6·0.4, 그날 최근 3건만 고치고 '정정 기록'·Revised 발송. 지시문 6-3, config/proviser.yaml reports, 예약 작업 23:00으로. 첫 자동 점검 CBRS 6.5·INIO 8.5·PWR 10.0. 시험 tests/test_report_audit.py
- 방위 섹터(§21.39, 마스터 2026-10-29): `config/defense.yaml`(부문 4·제품 대분류 10·기업 87, 독·프·이·스·일·미), 원천 2개(각국 국방 조달·예산 색인 / 방위 기업 뉴스룸 36곳 — war.gov 자동 접속 차단이라 색인만, 실측 3일 정부 14건·뉴스룸 47건), 펄스 🛡·판정 상향(방위 수주·DSCA), `knowledge/methods/defense_lens.md`, 발굴 방위 테마 6·후보 14, 일본 방위 13종목 적시공시·IR Q&A. rss 폴러 질의별 언어·도메인 귀속·채용 공고 거름.
- 시가총액 구간 엔진(§21.40, 마스터 2026-10-29): `scripts/tenbagger/bands.py` B0~B11(B6 $50–60B 추가), 구간 안 백분위·구간별 상위 3·10배 산술(출구 EV/매출·참조 시장)·구간 이동, 유니버스 366(시드 `config/tenbagger_universe.yaml` 77 + 감시 목록·발굴·방위), easyconomics `--stale`·`--put`(ECB 환율), EODHD 키 시 스크리너 자동. 첫 실행 10종목 실데이터. 시험 13개 추가(전체 191 통과).
- 유럽 방위 종목 추가(§21.39 개정, 마스터 2026-10-29 "Kongsberg, CSG 같은 유럽 방위 종목도"): 노르웨이·체코·스웨덴·영국·그리스·오스트리아·핀란드 15개사(기업 102) — 상장·티커 확인(CSG 2026-01 암스테르담, Kongsberg 해양 부문 2026-04 분리, Steyr Motors는 Red Cat 공개매수 진행), easyconomics `ec_ticker`, Kongsberg Maritime 제외 `not_titles`, 뉴스룸 14곳(실측 34건), 발굴 후보 9, BAE·CSG 시총 실데이터(CSG B2 $16.5B·BAE B8 $81.2B).
- 텐배거 리포트 개편(§21.41, 마스터 2026-10-29): 하루 3건(07·13·22시, chiip-tenbagger-report cron 변경), 자동 삽입 세 절 — 내러티브 다각(`narrative_view.py`), 수급 Chiip Flow(`flow.py`, FINRA 공개 API로 리테일 도매 체결 vs 기관·이상 거래일 원인), 월·주·일 피보나치 겹침(`levels.py`, ATR 지그재그·BLL 기준선·라운드 넘버), 렌더러 캔들·쌓인 막대, 금액 단위 `radar/units.py`($25B·$M·$T, notify·렌더 공통), 데이터 검증의 최신 재무상태표 대조, 상수 `config/report_tools.yaml`·등록부 7개. 첫 산출 PWR 3Q26(마스터 수동 지정 — 데이터 검증 10/10, v2 0.44배·시장 내포 CAGR 30%, 10배 경로 닫힘, 예측 P-20261029-12). 시험 19개 추가(전체 210 통과).
- 실시간 알림 3문단 양식(§21.42, 마스터 2026-10-29 "종목｜내용｜시간 → ☞ 회사 설명 3줄 → 핵심 내용 3개"): radar/notify.py format_item·company_profile·remember_profile·snippet_points, config/company_profiles.yaml(30일 캐시), radar-triage 출력 points·profile, run_poll 빠른 길 enrich(haiku 1회, 실패 시 요약문 문장), 묶음 발송 구분선. 시험 tests/test_alert_format.py
- 발굴 메커니즘 점검·조용한 매집형 상승(§21.43, 마스터 2026-10-29 "FormFactor·Nova 같은 엣지 중소형 반드시 관측 — 기관 자금이 들어오며 조용히 꾸준히 오르는 종목"): 빈틈 ① 구간 시드·발굴 후보가 레이더 인식·SEC 수집에서 빠짐 → common.discovery_entities·edge_watch_entries(일반어 이름은 aliases로만) ② 점수에 추세·매집 신호 없음 → scripts/discovery/quiet.py(정보 이산성·52주 고점·FINRA ATS 비중·리테일 비중·EPS 서프라이즈, 관문). 테마 metrology_inspection(Nova·Onto·Camtek)·probe_test에 FormFactor·Cohu, screen.py quiet 요소, 등록부 prm-quiet-w-*. 시험 tests/test_quiet.py
- 데이터 원천 Fiscal.ai 전환(§21.44·ADR-012, 마스터 2026-10-30): easyconomics 퇴역. knowledge/methods/data_fiscal.md(7개 기능 → 엔진 단계), scripts/fiscal/templates 7개(PWR 실측), scripts/fiscal/adapter.py, config/fiscal_keys.yaml, levels 장기 월봉. 운영 지시문·스킬·설정·스크립트 주석과 예약 작업 프롬프트 2개 교체. 시험 tests/test_fiscal_adapter.py
- 일본 결산설명회 Q&A 확보 절차(§21.45, 마스터 2026-10-30 지시문 A·B): 출처 등급 A~E(가이던스·수치는 A·B만), jp_ir_qa.py 우선순위·영문판·로그미 추적·IR 프로필·+3/+7영업일 재확인(TSE 휴장일)·지시문 B 대상 항목, 절차 문서 knowledge/methods/jp_ir_qa_procedure.md, 노션 '일본 IR 프로필' DB, 펄스 ⑥ 연결. 시험 tests/test_jp_ir_qa.py
- 대만 法說會·홍콩 실적 브리핑 Q&A 확보 절차(§21.46, 마스터 2026-10-30): tw_disclosure.py 召開法人說明會 감지(parse_conference·tw_ir_profile 빈도), 펄스 언어 필터 예외, 절차 문서 knowledge/methods/tw_hk_ir_qa_procedure.md(접근 판정 표·홍콩 유형 A~D), 노션 '아시아 IR 프로필'로 확장, coverage.yaml adr·hk_type 필드. 시험 tests/test_tw_ir.py
- 어닝 캘린더 Fiscal.ai 전환(마스터 2026-10-30 "어닝캘린더도 Fiscal.ai를 참조하라"): scripts/fiscal/templates/calendar.js(미국 티커 50개 묶음 + 회사 키 묶음, 확정·추정·예상·장전·장후), radar/markets/earnings_calendar.py --fiscal-code·--fiscal-put·fiscal_events·merge(한국은 KIND 보조 — Fiscal에 코스닥 없음·코스피 일부, EODHD는 예비), radar/portfolio.py 05시 이후 '실적 일정 갱신' 신호, config/fiscal_keys.yaml 1차 상장 키 6개. 실측 79건(10/29~11/20). 일봉 본보기 미확정 마지막 봉 제외(거래량 < 직전 20일 중앙값 1%). 시험 tests/test_fiscal_calendar.py
- 텐배거 리포트 노션 Stocks 게시·INNIO·Cerebras Fiscal.ai 재작성(마스터 2026-10-30): scripts/tenbagger/report_notion.py(JSON → 노션 마크다운, $ 이스케이프), publish_report.py --caption(텔레그램 = 캡션 + GitHub 링크만), 노션 '이니오 INIO'·'세레브라스 CBRS' 아래 10/30 리포트 하위 페이지(notion_log.csv). 두 리포트 컨센서스를 Zacks(Fiscal.ai history)로 교체 — INIO EPS 리비전 +4.3% → +1.7%(제출 2~3명·매출 추정 8월 초 이후 미갱신이라 방향 참고용), CBRS 어닝콜·컨센서스 절 추가. 감사 INIO 9.5·CBRS 9.4. 단위 버그 수정(숫자 뒤 B$가 '6.6$B'로 바뀌던 것, radar/units.py ⑤), 표 주석 렌더(report_html)
- 펄스 5분 주기·실적 건 분리(§21.26 개정, 마스터 2026-10-30 "Pulse는 10분이 아닌 5분마다", "여러 종목을 감지했을 때 어닝이 나오면 어닝 양식대로"): 예약 작업 chiip-pulse `*/5`, 잠금 9분 유지·한 회차 4분 목표·알파 회차당 2종목. 실적 건은 묶음에서 빼서 Dean's Ticker 3단, 실적 숫자엔 발표 전 Zacks est.(earnings_format.md: 매출·영업이익·EPS est. 의무, OCF·CAPEX·FCF 당분기, 이름 괄호 설명 금지). AMZN·SNDK 정정 발송.
- 어닝콜 전문 신규 게재 감시(마스터 2026-10-30 "콜이 끝나도 Fiscal.ai 스크립트가 늦게 올라온다 — 새로 올라오면 정리"): radar/transcript_watch.py(실적 일정 누적·발표 후 10일 대기·20분 간격·우선순위·이미 정리/--await) + scripts/fiscal/templates/transcript_check.js + 펄스 관문 transcripts.due·지시서 1-1(회차당 2건, tier 0·1 3단·나머지 ② 뉴팩트). 첫 확인 28건 중 15건 게재(PWR·CAT는 이미 정리, 13건 정리 대기). 같은 날: 텐배거 리포트 발행 묶음(GitHub 보관·claude.ai 보기·노션 임베드), 전력확장 기업 4곳 레이더 등록.
- 어닝콜 인사이트 피드(마스터 2026-10-30 "뒤늦게 올라오면 뉴팩트 정리와 함께 인사이트 피드도" · "뉴팩트에도 제목 아래 기업 설명 1줄"): 늦게 올라온 전문은 ②(·③) 다음 ④ 한 통 — 콜은 생중계로 이미 공개됐으니 콜 전용 사실·Q&A 답변 회피·반응 뒤 표류를 CIF로. scripts/fiscal/templates/call_feed.js(종가·대형주 6종 시장 근사·경쟁사·이번/직전 Q&A 통계) → scripts/insight/call_feed.py(반응 세션·반응일 AR·β·발표 전 20일 상승·표류·log.csv), config/insight/call_feed.yaml·등록부 prm-callfeed-* 3개, 기저율 call_qa_content·call_nonanswer, diffusion --callqa, transcript_watch --done은 ④ 파일 필요(--no-feed). earnings_format ④·② ☞ 줄, 지시서 1-1 d2
- 일본 IR 자료실 상시 감시(마스터 2026-10-30 "일본 기업은 PT 자료·Q&A 스크립트를 실적 보도 뒤에 늦게 낸다 — 공식 IR 사이트를 지속적으로"): radar/pollers/jp_ir_docs.py(src-jp-ir-docs, 10분 — 실적 구간 회사만 매 회차·평소 180분·회차당 45요청) — 자료실 페이지 자동 탐색, 결산 기간·날짜 파싱(年度 기준), 과거 아카이브 무시·첫 회차 기준선(최근 3일만), PT·短信은 직전 기간 자료와 함께 'IR 자료'(펄스 ⑥-2), Q&A·전문은 'IR 질의응답'(jp_ir_qa와 항목 id 공유), Q&A 대기·지시문 B 이관. 시험 tests/test_jp_ir_docs.py
- 소비재·게임·콘텐츠IP 발굴(Chiip Consumer, 마스터 2026-10-30 — 타카라토미 실적 +11% 계기, 설계안 승인 '이대로 구현'): config/consumer.yaml(30종목·국면 문턱·가중치) · knowledge/methods/consumer_lens.md · radar/consumer_attention.py(위키 조회·스팀 추천·애플 순위·브랜드 뉴스, run_hourly 하루 1회) · scripts/discovery/consumer.py(국면 판정·점수·株探 --kabutan·--put-q) · scripts/fiscal/templates/consumer.js · 펄스 '소비재' 클래스(지도 종목 실적·적시공시·급가속)·🛍 블록 · Ten-bagger d3·bands sectors.consumer · 레이더 종목 인식·수집 관문·SEC·기업 1줄·일본 적시공시/IR 자료실 10개사 · 등록부 prm-consumer-* 15개. 원천 점검: 아마존·레딧 직접·틱톡·스팀 리뷰 API·eir-parts.net은 robots 차단. 시험 tests/test_consumer.py
- 텐배거 리포트 양식 개정(마스터 2026-10-30): 맨 앞 내러티브 절(여섯 렌즈·제품·서비스·기술, narrative_view.lead_section)·배수 사다리(ladder.py — $30B 미만 2·3·5·10배, $30B~$100B 2·3·5배, $100B 이상 2배)·그림 고정 3·5·8(pin)·지난 12개월 EPS 리비전 추이와 최근 4개 분기 주가 분해(revision_view.py, eps_history.js)·논문 표기 제거(scrub). 알파 레이더 재실행 최상위 UCTT 7.3 리포트를 새 양식으로 재작성
- 텐배거 리포트 양식 2차 개정(마스터 2026-10-30): 리포트에서 데이터 제공처 이름·Zacks 표기 제거(구분은 '모델 추정'·'애널리스트 추정', 렌더러 scrub), 본문 아래 부가 설명 제거(업사이드 기준·차트와 표 주석·읽는 법), 전문 용어·영어 약자 기관명 한국어 풀이(config/report_glossary.yaml), 콜 변화 영향에서 확신도 가중 수치 제거, 분기별 서프라이즈 매출·OPM·EPS(EBITA Margin 대체 지원). UCTT 리포트 같은 링크로 재발행
- 한국 IR 자료 상시 감시(마스터 2026-10-30 재점검 후 지시): radar/pollers/kr_ir_docs.py·config/kr_ir.yaml — IRGO 종목 페이지 + 공식 자료실, 경영실적 자료·콜 스크립트를 펄스 ⑥-2·⑥으로, 그림 PDF는 원본 보관
- 텐배거 리포트 그림 5 단순화(마스터 2026-10-30): 계단선과 실적 발표일만, 사건별 변화는 그림 뒤 표로
- 한국 종목 기준 자료 = 당기·직전 분기 PT(마스터 2026-10-30): kr_ir_docs.py --pt, transcript_watch.py XKRX_ 대기 제외
- 기준 멀티플 = Fwd 1Y 이익 지표(마스터 2026-10-30): multiples.main_metric·choose_basis, forward_multiples.js, adapter --forward-multiples, 시장÷내재는 EV끼리
- 실적 지표 주가 줄(마스터 2026-10-30): 보고 시점 기준 장중·장전·장후 ±x%, radar/markets/session.py
- 그림 5 재개정(마스터 2026-10-30): 선 위 사건 번호만, 점선 없음, 번호별 설명은 그래프 아래
- 기준 멀티플 세 분류(마스터 2026-10-30): Fwd 1Y·2Y·3Y 그림 3개, 2·3Y는 같은 가격으로 분모만 바꾸고 3Y 모자란 분기는 마지막 연도 추정 성장률로 연장, 재료 없으면 merge 중단
- 원자력·위성 밸류체인 발굴(마스터 2026-10-31): discovery 테마 4개·watch 연결·구간 섹터 nuclear·space·분석 틀
- 원자력·위성 정부 원천(마스터 2026-10-31): src-nuclear-nrc·src-nuclear-doe·src-space-gov-gn, 펄스 ☢·🛰 분류, 판정 상향, rss.py exclude_regex 결함 수정
- TradingView 양방향 동기화(마스터 2026-10-31): radar/tv_sync.py, config/tradingview.yaml, tradingview_symbols.csv, 스킬 tv-sync, 예약 작업 chiip-tv-sync
- 실적 지표 주가 줄 필수화(마스터 2026-10-31): TradingView 시세 → radar/markets/session.py --line
- Laboratory 에이전트 트랙(마스터 2026-10-31): evals/rules.yaml·scripts/lab/rule_evals.py 규칙 측정, radar/pulse_check.py 건별 점검, 펄스 출처 링크 발송 관문, literature.py 에이전트 수집, 제안 AAP-20261031-01~03
- CLAUDE.md 분량 축소(마스터 승인 AAP-20261031-02): 출력 채널 기능별 규칙을 docs/channels/ 8개 파일로 이동, 공통 규칙과 색인만 유지
- 하네스 설계 ADR-013(마스터 지시 2026-10-31): 조사 1회차, literature.py Eugene Yan·Latent Space·하네스 검색어 추가, 변경 관문 잡음 폭·최소 표본 반영. 구현 단계는 승인 대기
- 하네스 1단계(마스터 승인 2026-10-31): radar/run_ledger.py 실행 장부, radar/verifier_lock.py 평가기 잠금·일일 점검, Proviser 문서 일정 표류 수정. 판정 2026-11-07
- 하네스 2단계(마스터 승인 2026-10-31): 펄스를 Windows 작업 chiip-pulse-trigger로 전환, 앱 예약 chiip-pulse 일시 중지. 판정 2026-11-14
- 실적 달력 날짜 수정(마스터 지시 2026-10-31): 미국 날짜에 한국 시각을 붙이던 calendar.csv·일정 알림을 한국 날짜로, upcoming.json의 date는 현지 날짜 유지(date_kst 추가)
- Weekly Review 발행 묶음(마스터 지시 2026-10-31): scripts/weekly/publish_weekly.py Artifact→노션→텔레그램, 마스터의 노션 Weekly 페이지 아래 주차별 게시

## 마스터 할 일
`docs/TODO_MASTER.md`
