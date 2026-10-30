# TradingView MCP 도구 목록

> 공식 커넥터(`https://mcp.tradingview.com/mcp`) 실조회 2026-10-31 01:30 KST. 베타라 바뀔 수 있으니 도구 이름은 이 문서가 아니라 실제 목록으로 다시 확인한다.
> 쓰기 도구는 마스터가 지시한 범위에서만 쓴다. 시세를 쓸 때마다 `update_mode`로 지연 여부를 적는다.

## 와치리스트

| 도구 | 구분 | 입력 → 출력 |
|---|---|---|
| `mcp-watchlist-list-watchlists` | 읽기 | 없음 → 전체 리스트(id·이름·종목 배열·`###` 섹션 표시) |
| `mcp-watchlist-get-watchlist` | 읽기 | id → 리스트 내용. 다른 사용자의 공개 리스트도 읽기 전용으로 열린다 |
| `mcp-watchlist-get-active-watchlist` | **읽기(부작용 주의)** | 없음 → 활성 리스트. 활성 리스트가 없으면 활성화하고, 리스트가 하나도 없으면 새로 만든다 |
| `mcp-watchlist-add-to-watchlist` | 쓰기 | id·종목 → 추가. **이미 있는 종목은 맨 뒤로 옮긴다** |
| `mcp-watchlist-create-watchlist` | 쓰기 | 이름·종목(선택) → 새 리스트 |
| `mcp-watchlist-update-watchlist` | 쓰기 | id·이름·설명 → 이름·설명 변경 |
| `mcp-watchlist-remove-from-watchlist` | 쓰기(제거) | id·종목 → 제거 |
| `mcp-watchlist-delete-watchlist` | 쓰기(삭제) | id → 리스트 삭제 |

## 시세·종목

| 도구 | 구분 | 입력 → 출력 |
|---|---|---|
| `mcp-tv-search-symbols` | 읽기 | 티커·회사명 → `EXCHANGE:TICKER` 후보 |
| `mcp-tv-get-symbol-data` | 읽기 | 종목·열 → 스크리너 열 값 |
| `mcp-tv-get-symbol-data-batch` | 읽기 | 최대 50종목·열 → 값, 못 찾은 종목은 `missing` |
| `mcp-tv-get-ohlcv` | 읽기 | 종목·간격·기간 → 봉(1회 최대 5,000행 또는 8,000열). **정규장만**, 마지막 봉은 형성 중 |
| `mcp-tv-get-screener-columns` | 읽기 | 묶음·검색어 → 쓸 수 있는 열 이름 |
| `mcp-tv-run-screener` | 읽기 | 필터·정렬·열 → 스크리너 결과(최대 1,000행) |
| `mcp-tv-get-technicals-rating` | 읽기 | 종목·간격 → 기술 지표 묶음 |

## 재무·추정·문서·뉴스·일정

| 도구 | 구분 | 입력 → 출력 |
|---|---|---|
| `mcp-tv-get-financials` | 읽기 | 종목·지표·기간 → 현재 재무 지표 |
| `mcp-tv-get-financial-history` | 읽기 | 종목·분기/연간 → 재무 이력 |
| `mcp-tv-get-forecasts` | 읽기 | 종목 → 의견·목표가·EPS·매출 추정 |
| `mcp-tv-get-documents` | 읽기 | 종목·분류·기간 → 공시·전문·발표 자료 목록과 view id |
| `mcp-tv-get-document-view` | 읽기 | view id → 문서 본문(요약·전문) |
| `mcp-tv-get-news` | 읽기 | 종목·언어 → 제목(최대 200건) |
| `mcp-tv-get-news-story` | 읽기 | 기사 id → 본문 |
| `mcp-tv-get-earnings-calendar` | 읽기 | 종목 → 다음·직전 실적일과 추정 |
| `mcp-tv-get-dividends-calendar` | 읽기 | 종목 또는 시장·기간 → 배당 일정 |
| `mcp-tv-get-economic-calendar` | 읽기 | 국가·중요도·기간 → 경제 일정 |
| `mcp-tv-get-economic-data` | 읽기 | `ECONOMICS:` 코드·기간 → 시계열 |
| `mcp-tv-get-economic-symbols` | 읽기 | 분류·국가·검색어 → 경제 지표 코드 |

## 알림

| 도구 | 구분 | 입력 → 출력 |
|---|---|---|
| `mcp-tv-list-alerts` | 읽기 | 상태·종목 → 알림 목록 |
| `mcp-tv-get-alerts` | 읽기 | 알림 id → 조건 포함 상세(메시지·웹훅 주소 제외) |
| `mcp-tv-get-alerts-log` | 읽기 | 기간·종목 → 발동 이력 |
| `mcp-tv-create-alert` | 쓰기 | 종목·가격 조건 → 알림 생성. 복합·지표 조건과 웹훅은 불가 |
| `mcp-tv-update-alert` | 쓰기 | 알림 id·설정 → 수정 후 재시작 |
| `mcp-tv-stop-alerts` | 쓰기 | 알림 id → 일시 중지 |
| `mcp-tv-restart-alerts` | 쓰기 | 알림 id → 재개 |
| `mcp-tv-delete-alert` | 쓰기(삭제) | 알림 id → 삭제(발동 이력 포함) |

## 시세 지연 실측 (2026-10-31 01:30 KST, 마스터 계정 기준)

| `update_mode` | 뜻 | 확인한 거래소 |
|---|---|---|
| `streaming` | 실시간 | NASDAQ, NYSE, AMEX, LSE, TVC(미 10년물), COINBASE |
| `delayed_streaming_900` | 15분 지연 | EURONEXT, XETR, HKEX, TSX |
| `delayed_streaming_1200` | 20분 지연 | KRX, TSE |

NVDA 1분봉의 마지막 봉은 조회 26초 전에 시작한 현재 분 봉이었다. 값은 계정의 거래소 구독에 따라 달라지므로 코드에 고정하지 않고 조회할 때마다 `update_mode`를 읽는다.

## 장전·장후 시세

`get-ohlcv`는 정규장만 주지만 스크리너 열 `premarket_change`·`premarket_close`·`postmarket_change`·`postmarket_close`로 장전·장후 값을 받을 수 있다. 시장마다 비어 있는 칸이 있다(2026-10-31 조회: KRX는 장후 값 있음·장전 없음, TSE는 둘 다 없음, XETR·NVDA는 장전 값 있음). 값이 비면 지어내지 않는다.

## 와치리스트 표기 주의

- `###이름`은 종목이 아니라 **섹션 구분**이다. 보이지 않는 문자가 섞인 섹션 이름이 있어 손으로 다시 치지 않고 조회 결과를 그대로 쓴다.
- 환율로 나눈 값(`KRX:000660/FX_IDC:USDKRW`)과 스프레드처럼 종목이 아닌 항목이 있다.
- 같은 회사가 다른 거래소 코드로 들어 있을 수 있다. 매핑은 코드뿐 아니라 회사 기준으로 확인한다.
