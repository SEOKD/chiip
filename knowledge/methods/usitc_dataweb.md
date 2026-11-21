# USITC DataWeb 연결 방법 (2026-11-21 마스터 지시)

> 주 경로는 미국 Census 국제무역 API(`radar/trade_share.py`)다. DataWeb의 원천이 Census라서 값이 같다(2026-11-21 라면 HTS 1902300060 한국 비중 6개월 대조 일치).
> DataWeb은 Census API에 없는 칸이 필요할 때만 쓴다: 관세액(calculated duties), 통관 항구(district), 특혜 프로그램(USMCA·KORUS 등), 소비용 수입.

## 마스터가 할 일(한 번, 약 10분)
1. https://dataweb.usitc.gov/sign-in 에서 무료 계정을 만든다. 로그인은 Login.gov 계정과 연결한다(안내: https://www.usitc.gov/dataweb_login_process).
2. 로그인한 뒤 오른쪽 위 **API** 탭 → **Generate Token**으로 토큰을 만든다. 토큰은 **6개월 유효**이고 자동으로 갱신되지 않는다.
3. 토큰을 `D:\local-only\secrets\.env`에 `USITC_DATAWEB_TOKEN=...` 한 줄로 넣는다(저장소·대화에 붙이지 않는다).
4. DataWeb 화면(https://dataweb.usitc.gov/trade)에서 **New Request**로 질의를 만들고 이름을 붙여 저장한다(Save a Copy). 예 — 라면 그래프:
   - Step 1 Trade Flow: Imports: General(또는 For Consumption) · Classification: HTS Items
   - Step 2 Data: Customs Value, First Unit of Quantity · Timeframe: Monthly
   - Step 3 Countries: Display Countries Separately
   - Step 4 Commodities: 1902.30.0060 · Aggregation Level HTS-10
   - Step 11: Save Query Name `ramen_kr_share`

## Chiip이 하는 일
- `py radar/usitc_dataweb.py --list` → 저장한 질의 이름 목록.
- `py radar/usitc_dataweb.py --run ramen_kr_share` → `knowledge/models/consumer/dataweb/ramen_kr_share.json`.
- 호출 구조(공식 안내 https://www.usitc.gov/applications/dataweb/api/dataweb_query_api.html):
  - 기준 주소 `https://datawebws.usitc.gov/dataweb`, 헤더 `Authorization: Bearer <토큰>`.
  - `GET /api/v2/savedQuery/getAllSavedQueries` → 저장한 질의 목록.
  - `POST /api/v2/report2/runReport`(본문 = 저장한 질의 JSON) → `dto.tables[측정값 순번]`에 열 머리와 행.
- 토큰이 없으면 아무것도 하지 않는다. 토큰 발급 전이라 실제 호출은 아직 시험하지 못했다(첫 실행에서 응답 구조를 확인한다).

## 확인하지 못한 것
- API 호출 한도 수치와 이용 약관 본문: usitc.gov가 자동 요청(프로젝트 User-Agent)에 403을 돌려줘 robots.txt를 읽지 못했다. 공식 안내 페이지는 브라우저로 읽었다. 토큰을 쓰는 API는 USITC가 공개 안내한 정식 경로이고, 미국 연방 정부 통계는 공공 저작물이다.
- 그래서 DataWeb 호출은 하루 1회·저장한 질의 단위로만 쓴다.
