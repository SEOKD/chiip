# 데이터 원천 운영 규칙

- **데이터 추출 우선순위**(2026-11-01 마스터 지시 "Fiscal.ai를 1순위, Easyconomics와 Zacks를 2순위로. Easyconomics도 호출 제한이 있으니 같은 우선순위인 Zacks와 번갈아 쓰고, 2순위 채널끼리 서로 보완할 부분이 있으면 보완하는 구조도 만들어라", ADR-014, 아래 2026-10-30 '퇴역·호출 금지'보다 우선):
  - Fiscal.ai 칸이 비었을 때만 2순위를 부른다. 항목별 경로는 `config/data_sources.yaml`.
  - 두 채널이 모두 내는 항목(지난 분기 추정 매출·EPS, 의견 분포·목표가)은 `py scripts/fiscal/source_router.py next <항목>`이 회차마다 번갈아 고른다. Easyconomics를 부르면 `used easyconomics`, 호출 제한 응답을 받으면 `limited easyconomics`를 기록한다. 하루 상한은 `limits`(실제 한도 미확인, 보수적 값).
  - 보완: 차례인 채널에 빈칸이 남으면 다른 채널이 채운다. `scripts/fiscal/estimates.py`가 한다. Easyconomics는 실적이 Fiscal.ai 실적과 2% 안에서 맞을 때만 쓴다(응답에 깨진 칸이 있고 EPS 기준이 다를 수 있다). 두 채널 추정이 10% 넘게 벌어지면 출력에 표시한다.
  - 한쪽만 내는 항목: Zacks = EBIT·EBITDA 추정, EPS 리비전 이력, 과거 Fwd 멀티플. Easyconomics = 상향·하향 피드, 일본·대만·유럽 요약 재무, 포지셔닝·유동성·매크로.
  - Easyconomics `company_profile`은 응답의 출처 표시가 yfinance다. `company_ratios`는 응답이 매우 커서 쓰지 않는다. 라이선스는 비공개 산출물에만.
- **Chiip Analysis 2순위 세 채널**(2026-11-01 마스터 지시 "1순위 Fiscal.ai, 2순위 Easyconomics, Zacks, yfinance. 한 가지 방법만 쓰지 말고 세 가지를 모두 써라. 세 가지 모두 균형 있게", 위 번갈아 쓰기보다 우선):
  - 리포트마다 세 채널을 모두 호출하고, 지금까지 덜 쓴 채널부터 빈칸을 채운다. 누적 사용량은 `radar/state/data_sources.json` `served`, 확인은 `py scripts/fiscal/source_router.py status`.
  - **yfinance 직접 호출 금지.** finance.yahoo.com robots.txt가 ClaudeBot·anthropic-ai를 전면 금지하고 query1 API는 모든 봇을 금지하며, 라이브러리가 의존하는 `curl_cffi`는 브라우저 위장 용도로 쓰인다. Easyconomics `company_profile`의 yfinance 출처 자료만 쓴다.
  - Easyconomics `earnings_summary_dates`와 `company_profile` 추정은 값이 거의 같다(FORM 4개 분기 확인). 원출처가 같을 가능성이 커서 두 채널의 일치를 독립 확인으로 세지 않는다.
- **발표 전 추정 저장**(2026-11-01): 발표 10일 안의 종목은 매일 Fiscal.ai 추정을 `knowledge/models/estimates/snapshots.csv`에 쌓는다(값이 바뀔 때만). Chiip Portfolio의 그날 첫 일정 갱신 회차가 돌린다.

> CLAUDE.md '출력 채널'에서 옮긴 마스터 지시(2026-10-31, AAP-20261031-02). 새 지시도 여기에 적는다.

- **데이터 원천 = Fiscal.ai(MCP)**(2026-10-30 마스터 지시 "Pulse·Portfolio·Ten-bagger·Reporter·Analysis·Notion Tracker·Model Laboratory·Proviser·Weekly Review는 Easyconomics를 쓰지 말고 Fiscal.ai만 — 7가지 기능 모두", ADR-012): easyconomics MCP는 **퇴역**(호출 금지). 뉴스(종목·톱뉴스·중요도 1~5)·컨센서스(Zacks 평균·분산·5년 리비전·목표가·의견 + Fiscal 자체 추정·가이던스 출처)·재무/세그먼트/일별 배수/일봉·IR/트랜스크립트(Q&A·화자)/실적 일정·13F/내부자·펀드 레터·피어/Fiscal 포트폴리오(읽기 전용)를 `execute_code` 본보기 `scripts/fiscal/templates/*.js`로 받고 `scripts/fiscal/adapter.py`로 엔진 파일에 넣는다(데이터 계약 `knowledge/methods/data_fiscal.md`, 회사 키 `config/fiscal_keys.yaml`). **Zacks 수치를 보여 줄 때마다 'Data provided by Zacks Investment Research, Inc., www.zacksdata.com' 표기.** 일봉에 고가·저가가 없어 근사 표기, 공매도 거래량은 FINRA, 매크로는 FRED 공개 자료(Portfolio 시장 국면), 포지셔닝은 쓰지 않는다. fiscal.ai 링크는 응답의 auditUrl·terminalUrl만(손으로 만들지 않는다).
- **컨센서스 채널 확장**(2026-11-01 마스터 지시): Chiip Proviser가 매 회차 `config/consensus_channels.yaml`을 보고 기사 인용값을 모으고 후보 채널 하나를 검토한다(`docs/tasks/chiip-proviser.md` 6-5, `scripts/fiscal/cited.py`).
  - 기사 인용값은 `knowledge/models/estimates/cited.csv`에 제공사·매체·주소·게재 시각·기간·기준과 함께 쌓는다. 제공사 직접 데이터가 아니고 est. 비교에 넣지 않는다. 순위와 표기 문구는 마스터 결정 대기.
  - CNBC·Reuters·MarketWatch·Barron's·Seeking Alpha는 robots.txt가, Investing.com은 저장소 기록상 약관이 막아 직접 열지 않는다. 검색 결과에 보이는 값만 쓴다.
  - TradingView `mcp-tv-get-forecasts`는 후보 채널이다. 응답에 원제공사 표시가 없다.
