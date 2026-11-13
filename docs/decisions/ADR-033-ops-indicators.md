# ADR-033 Analysis 운영 지표 3종 + 사업별 매출 vs 물가 (2026-11-14)

## 맥락
마스터 지시(2026-11-14): "Rule of 40은 소프트웨어 종목의 Analysis에 사용하라", "옵션 내재 변동폭, 수주/출하 비율 × 재고도 만들어라", "CPI·PPI 격차는 기업의 제품 및 서비스 매출과 비교할 때 써라".
같은 날 점검에서 '어닝콜 변화' 절(`report_layout.earnings_blocks`)이 정해진 두 표만 고르기 때문에 6331f29의 추정치 수정 폭 블록이 리포트에서 빠진다는 것도 드러났다.

## 결정
1. **재료** `scripts/fiscal/templates/ops_metrics.js` → `py scripts/tenbagger/ops_view.py --put <id> <파일>` → datapack `ops`:
   분기 재고(재무상태표)·영업현금흐름·CAPEX(현금흐름표)·수주·수주잔고(KPI 'Total Orders'·'Bookings'·'Backlog'·'RPO')·매출·매출원가(quarters_hist가 없을 때).
2. **Rule of 40**(소프트웨어 — industry 'software' 또는 sector_kpis.lens 'software'): 4개 분기 매출 성장% + FCF 마진%, 주식보상 차감판(독립 리서처 관행 — 주식보상은 실제 비용), 4개 분기 추이. '섹터 핵심 지표' 절(`sector_view`)에 싣는다 — sector_kpis가 없어도.
3. **수주/출하 × 재고**: B/B(분기·4분기) × 재고 일수·재고 증가율 vs 매출 증가율 → 사이클 사분면(상향 국면 / 수요 강함+재고 축적 / 하향 경고 / 재고 조정). 새 절 '수주·출하·재고 사이클'(재고가 있는 회사만). 수주 미공시면 B/B 칸을 쓰지 않는다.
4. **실적 발표 예상 변동폭**: 옵션 내재 = 실적일 직후 만기 ATM 스트래들 ÷ 주가, 과거 실적일 다음 거래일 실제 움직임(revision_events × ohlcv)과 비교(>1.2배 = 불확실성 프리미엄, <0.8배 = 작게). 옵션 자료가 없으면 과거 움직임만.
   원천: Cboe 지연 시세 JSON(cdn-api.cboe.com — 일반 요청으로 IV·호가 제공). Fiscal.ai·TradingView·Easyconomics(GEX는 최대 고통·풋콜 비율만)에는 IV가 없다(2026-11-14 확인).
   **자동 수집은 꺼 둔다**(`config/ops_view.yaml options.enabled: false`) — 약관상 자동 수집 허용 여부가 애매해 마스터 판단을 받는다(CLAUDE.md). `radar/options_implied.py --put`(수동 입력)은 늘 쓴다.
5. **사업별 매출 vs 물가**(`input_view.segment_rows`): datapack `pricing` 항목(사업 ↔ 비교 지수 — 제품·기업 대상은 PPI, 소비자 대면 서비스는 CPI)을 `segments_hist`의 사업 매출과 맞춰(`segment` 키 또는 이름 앞부분) 전년 대비 명목 성장 − 물가 = 실질(물량·믹스). 마진 구조 절 문장 하나 + 그림 '사업별 매출 vs 물가'(한눈에 보기로 자동 이동).
6. `report_layout.earnings_blocks`가 '추정치 수정 폭'·'실적 발표 예상 변동폭'의 문단·표도 싣는다.

## 근거
- Rule of 40: 성장과 수익성의 교환을 한 숫자로(Bessemer·McKinsey 실무 기준선 40). 주식보상 차감은 SaaS 비판론(독립 리서처·Substack)의 표준 보정.
- B/B × 재고: 반도체·장비 사이클 분석의 기본 짝(수요 선행 = 수주, 공급 과잉 신호 = 재고). 둘 중 하나만 보면 '주문이 많아 쌓이는 재고'와 '안 팔려 쌓이는 재고'를 못 가른다.
- 옵션 내재 변동폭: 실적 이벤트 프리미엄의 시장 가격(스트래들 ≈ 기대 절대 움직임). 과거 실제 움직임과의 비가 실무 비교 기준.
- 실질 = 명목 ÷ 물가: 가격 효과와 물량 효과의 분리(디플레이터의 표준 사용).

## 한계·반증
- 문턱(40·B/B 1.0·재고 격차 5%p·1.2/0.8배)은 사전값 — 등록부 prm-ops-*, 앞으로의 성과로 피팅.
- 주식보상 비율은 datapack 값 하나를 모든 분기에 쓴다(분기별 SBC가 들어오면 바꾼다). Fiscal 현금흐름 분기값이 누계로 보이면(10-Q YTD) 확인 필요.
- 세그먼트 매출과 물가 지수의 범위가 다를 수 있다(회원 회비 ↔ 클럽 회비 CPI). '실질'은 물량·믹스 근사다.
