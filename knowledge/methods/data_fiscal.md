# 데이터 원천 = Fiscal.ai (MCP) — 엔진 데이터 계약

> 마스터 지시(2026-10-30): "Chiip Pulse·Portfolio·Ten-bagger·Reporter·Analysis·Notion Tracker·Model Laboratory·Proviser·Weekly Review는 앞으로 Easyconomics를 쓰지 말고 Fiscal.ai만 MCP로 연결해 써라. 7가지 기능을 모두 쓰도록 하라. 지금부터 시스템 엔진 아키텍처에 전부 반영하라." → ADR-012.
> easyconomics MCP는 **퇴역** — 어떤 기능도 부르지 않는다(과거 산출물의 'easyconomics' 출처 표기는 기록으로 둔다).

## 1. 호출 방식
- 도구: `mcp__…__execute_code`(자바스크립트 `async () => { … }`, 네트워크 격리 샌드박스 60초, 동시 6개) + `mcp__…__api_docs`(함수 시그니처 — 기억이 아니라 여기서 확인). ToolSearch로 `select:mcp__4056a804-908b-4b7a-b720-ace3a2bcabc9__api_docs,mcp__4056a804-908b-4b7a-b720-ace3a2bcabc9__execute_code`.
- **샌드박스 안에서 줄이고 계산한다** — 원자료 전체를 돌려받지 말고 필요한 열·기간만, 집계(월봉·주봉·합계)까지 끝낸 한 줄 JSON/CSV를 `console.log`. 큰 묶음은 단계로 나눈다.
- 회사 키 `<EXCHANGE>_<TICKER>`(예 `NYSE_PWR`, `NASDAQ_FORM`). 감시 목록 id → 키는 `config/fiscal_keys.yaml`에 캐시(처음엔 `company_profile`로 NYSE_/NASDAQ_ 순서로 확인해 적는다). 한국·일본·대만 상장사는 키·데이터 범위를 확인하고, 없으면 '미확인'.
- 본보기 코드: `scripts/fiscal/templates/*.js`(파일을 읽어 `__KEY__` 등을 바꿔 execute_code에 넘긴다). 텐배거 리포트의 최근 4개 분기 서프라이즈(Non-GAAP 실적 vs 발표 직전 추정)는 `surprise.js`. 어닝콜 전문 신규 게재 확인은 `transcript_check.js`(`radar/transcript_watch.py --code` → execute_code → `--put`, 2026-10-30 — 콜 직후엔 전문이 없고 몇 시간~며칠 뒤 올라온다). 실적 지표 정리의 `(est. …)`는 `earnings_est.js` — 지표마다 Fiscal.ai 자체 추정(발표 전 asOf 칸, 분기 환산값 포함 source 무관)을 1순위, Fiscal 칸이 없을 때만 Zacks 발표 전 마지막 값을 고른다. 컨센서스 묶음 `consensus.js`도 `fiscal` 블록이 1순위(2026-10-30 마스터 지시)(마스터 지시 2026-10-30, `knowledge/methods/earnings_format.md`). 출력 → 파일은 `scripts/fiscal/adapter.py`가 데이터 묶음·펀더멘털·일봉으로 바꾼다. 텐배거 리포트 그림 5·8의 EPS 추정 이력은 `eps_history.js` → `adapter.py --eps-history`(2026-10-30). 일봉 본보기(`prices.js`·`fundamentals.js`)는 마지막 봉의 거래량이 직전 20일 중앙값의 1% 미만이면 미확정 봉으로 보고 뺀다(장중·당일 행이 수백 주로 온다).
- 링크: 데이터 출처 링크는 응답의 `auditUrl`(공시 원문 페이지)·`originalSourceUrl`, 회사 링크는 `company_profile.terminalUrl` — **fiscal.ai·api.fiscal.ai 주소를 손으로 만들지 않는다**(api.fiscal.ai는 키가 필요해 깨진다).

## 2. 7개 기능 → 엔진 단계
| 기능(함수) | 쓰는 곳 | 규칙 |
|---|---|---|
| ① **뉴스** `company_news`(14일 기본·최대 31일, 유형 19개·중요도 1~5) · `top_news`(전 종목 7일, 시총 필터) · `company_news_summary`(종목별 일간 마크다운) | Pulse 속보 판단·미보도 확인(이미 보도됐는지), Portfolio 데일리, Reporter 야마 후보(중요도 1~2), Ten-bagger 신호(partnership·ma·guidance), 실시간 레이더 보강 | 중요도 1~2만 판단 대상, 3 이상은 참고. 뉴스 요약문은 사실이 아니다 — 1차 출처(sourceUrl·공시)로 확인. 뉴스는 9개 매체 제한과 별개(원천: Fiscal.ai 집계) |
| ② **컨센서스·추정치** `company_analyst_estimates`(Zacks: 매출·EPS·EBITDA·EBIT·세전이익·마진의 평균·중앙·최고·최저·표준편차·애널리스트 수, `history:true` 5년 변경 이력) · `company_analyst_ratings`(목표가 분포·의견 분포) · `company_estimates`(Fiscal.ai 자체: 가이던스 + 모델, 가이던스 원문 출처) | 데이터 묶음 consensus(연·분기, 최저·최고·애널리스트 수) · **consensus.revisions = history로 직접**(같은 분기끼리) · guidance(회사 가이던스 원문 링크) · 내러티브 셀사이드 층(목표가 분산·의견) · Portfolio IB 커버리지 · 실적 서프라이즈 | **Zacks 표기 의무**: Zacks 수치(컨센서스·목표가·의견·Street 선행 배수)를 보여 줄 때마다 그 수치에만 "Data provided by Zacks Investment Research, Inc., www.zacksdata.com"(링크 https://www.zacksdata.com). Fiscal.ai 자체 추정·가이던스·재무는 Zacks가 아니다. Zacks는 미국 상장·달러 기준 — 한국 원주 등은 비어 있을 수 있음(그때 '미확인', 노션 Stocks 마스터 입력·회사 자료로) |
| ③ **재무·세그먼트** `company_financials_as_reported`·`company_financials_standardized`(값마다 원문 페이지 auditUrl) · `company_segments_and_kpis` · `company_adjusted_metrics` · `company_ratios`·`company_daily_ratios`(일별 배수 시계열) · `company_stock_prices`(일봉: 시가·종가·거래량) · `company_shares_outstanding` · `company_stock_splits` | 데이터 묶음 raw(최근 4분기 GAAP·재무상태표·주식 수 — datapack_check 대조 원천) · history.ev_sales = daily ratios · 일봉 ohlcv(수급·피보나치) · 세그먼트 KPI(어닝콜 변화·밸류 동인) · 펀더멘털(구간·조용한 상승) | 일봉에 **고가·저가가 없다** → 캔들·CLV는 근사(고가 = max(시가, 종가), 저가 = min(…)) — 리포트에 '근사' 표기. 세그먼트 컨센서스는 없음 |
| ④ **IR·어닝콜** `company_ir_events`(보고서·슬라이드·보도자료 PDF·녹음) · `company_ir_events_transcript`(화자 구분·타임스탬프·Q&A 구간) · `events_calendar`(과거·예정 실적) · `company_earnings_summary` · `company_filings`·`filing_pdf`·`filing_page_image` | 어닝콜 변화(직전 콜 대비 deltas) · **애널리스트 질문만 뽑기**(Q&A 구간·화자 역할) → 셀사이드 내러티브 초점 · Dean's Ticker 3단 양식 · **실적 일정 텔레그램**(2026-10-30 마스터 지시 "어닝캘린더도 Fiscal.ai를 참조하라" — `calendar.js`: 미국 티커 50개 묶음 + 그 밖 회사 키 묶음, 확정·추정·예상·장전·장후. `radar/markets/earnings_calendar.py --fiscal-code` → execute_code → `--fiscal-put`, 05시 이후 그날 첫 chiip-portfolio 회차가 갱신. 한국은 KIND IR일정을 보조로 유지 — Fiscal에 코스닥 상장사가 없고 코스피도 일부만. 1차 상장 키로 풀리는 종목(TSMC→NYSE_TSM·ASE→NYSE_ASX·SAP→NYSE_SAP·Nokia→NYSE_NOK)은 `config/fiscal_keys.yaml`) · 펄스 속보 판단의 1차 서류 | 트랜스크립트는 라이선스 자료 — 요지만 자기 말로, 인용 15단어 이하. 바이너리(PDF·이미지)는 링크만 필요하면 받지 않는다 |
| ⑤ **수급·지분** `company_insider_holders`·`company_insider_transactions` · `company_institutional_holders`(13F, 분기 지정 가능) · `holder_institutional_holdings`·`institutional_holders_list` | Chiip Flow 보강(분기 기관 보유 변화 = 바이사이드 층) · 조용한 매집형 상승의 accumulation(13F 보유 증가 기관 수·비중) · Portfolio 내부자 매매 · 숏 리포트 수급(락업·내부자 매도) | 13F는 분기 45일 지연 — 날짜를 붙인다. FINRA 일·주간(장외·리테일)은 그대로 병행 |
| ⑥ **펀드 레터** `company_fund_letters` · `fund_letters`·`fund_letter`·`fund_letter_investors`·`fund_letter_companies` | 내러티브 바이사이드 층(어느 펀드가 롱/숏·확신도·비중·촉매·리스크·밸류 논리) · 텐배거 발굴 신호(소형주를 새로 산 펀드) · insight-review 반대 근거 | 원문 인용은 15단어 이하·출처(펀드·분기). 펀드의 의견은 사실이 아니라 '기대의 증거' |
| ⑦ **기타** `company_peers`(세그먼트 단위 경쟁 관계) · `companies_list` · `terminal_list_portfolios`·`terminal_get_portfolio`·`terminal_get_portfolio_transactions`(읽기 전용) | 데이터 묶음 peers 고르기(세그먼트 경쟁사 우선) · 멀티플 엔진 동종 · Portfolio가 config/portfolio.yaml과 Fiscal 포트폴리오를 대조(불일치만 알림, 쓰기 권한 없음) | 포트폴리오 쓰기 도구는 권한 없음(쓰지 않는다) |

## 3. 기능별 사용 (9개 예약 작업)
| 기능 | 주로 쓰는 Fiscal.ai |
|---|---|
| Chiip Pulse | ①(속보·미보도 확인·중요도) ②(실적 서프라이즈·리비전) ④(1차 서류·트랜스크립트 Q&A) ⑤(숏 리포트 수급) ③(시총·배수) |
| Chiip Portfolio | ①(종목 뉴스·일간 요약) ②(IB 커버리지 = 목표가·의견 분포 변화) ④(실적 일정·콜) ⑤(내부자·13F) ⑦(Fiscal 포트폴리오 대조) |
| Chiip Ten-bagger(발굴) | ③(구간·조용한 상승 펀더멘털·일봉) ⑤(13F 매집) ⑥(펀드 레터 신규 매수) ①(partnership·ma) ⑦(세그먼트 경쟁사) |
| Chiip Analysis(텐배거 리포트) | 7개 전부 — 데이터 묶음(③②④)·내러티브(②⑥①)·수급(⑤+FINRA)·피보나치(③ 일봉)·동종(⑦) |
| Chiip Reporter | ①(top_news 중요도 1~2·종목 뉴스) ④(실적 일정·1차 서류) ⑥(펀드 레터 논지 — 기사 각도) |
| Chiip Notion Tracker | ②④(마스터 글 검토의 숫자 검증) ⑥(반대 근거) |
| Chiip Model Laboratory | ②(Zacks 5년 리비전 이력 = 리비전 신호 피팅 자료) ③(일별 배수·가격 = 사이클 밴드·멀티플 피팅) ⑤(13F = 매집 요인 피팅) |
| Chiip Proviser | ③②(리포트·펄스 숫자 재대조 — auditUrl로 원문 페이지) |
| Chiip Weekly Review | ①(주간 top_news) ②(리비전 변화) — 예측 판정의 사실 확인 |

## 4. 대체 대응(easyconomics → Fiscal.ai)
| easyconomics(퇴역) | Fiscal.ai |
|---|---|
| company_profile(가격·시총·배수) | company_profile + company_stock_prices(최근 종가) + company_shares_outstanding + company_daily_ratios(시총·EV/매출·PER) |
| company_price_history | company_stock_prices |
| company_financial_statements·financials_summary | company_financials_standardized·as_reported |
| company_ratios | company_ratios·company_daily_ratios |
| earnings_summary·earnings_summary_dates | company_earnings_summary·company_ir_events·events_calendar |
| earnings_call_transcript·analyst_qa_calls | company_ir_events_transcript(Q&A 구간·화자 역할) |
| analyst_rating_changes | company_analyst_ratings(현재 분포) + history로 변화 |
| company_peers | company_peers |
| company_insider_buys·altdata(일부) | company_insider_transactions·holders, company_institutional_holders |
| company_short_volume | **없음** — FINRA 공개 API(scripts/tenbagger/flow.py)로 계속 |
| market_positioning·macro·liquidity | **없음** — 쓰지 않는다(필요하면 다른 공식 원천을 따로 승인받는다) |
| company_ir_events·news | company_ir_events·company_news·top_news |

## 5. 경계
- Fiscal.ai 응답의 뉴스 요약·펀드 레터·트랜스크립트는 라이선스 자료 — 저장소에는 메타데이터·자기 말 요약·링크만, 원문 전체 복제 금지.
- invest·public 모드 규칙 그대로(Zacks 표기 포함). 공개 채널 게시 금지.
- 하루 호출 한도·샌드박스 시간 초과는 기록하고 다음 회차로(무한 재시도 금지).
