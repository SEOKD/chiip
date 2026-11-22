# Chiip Industry Quarterly — 분기 결산 산업 리포트 절차 (ADR-018, 마스터 결정 2026-11-08)

마스터 결정: ① 산업마다 따로 쓴다 ② 산업별 구성 매출 80% 발표 관문(또는 분기 말 + 55일) ③ 아시아 종목 가이던스·재고 빈칸은 국내 증권사 공개 요약으로 보완 ④ 2026년 3분기 시험판(NAND·스토리지, 2026-11-08 발송).
운영 규칙: `docs/channels/industry.md`. **Industry Indepth 작업(chiip-industry-weekly, 매일 07:00)이 회차를 연다**(2026-11-08 마스터 지시, 그전엔 Pulse) — `py radar/industry_quarter.py`(status)의 `due`.

## phase: collect — 시즌 중 하루 한 번
1. `py radar/industry_quarter.py --plan <산업>`을 `industries`의 산업마다(한 회차에 최대 3개) 돌린다.
   - Fiscal 묶음 본문(scripts/fiscal/templates/quarter_batch.js)은 execute_code로 차례로(묶음 안 동시 6호출 이하) → 출력을 파일로 → `py radar/industry_quarter.py --put <산업> <파일>`.
   - `tradingview` 목록(한국·일본·대만 등)은 `mcp-tv-get-financial-history`(fq)를 한 종목씩(동시 호출 금지) → `[{id, currency, period_end, labels, series}]`(series = revenue·gross_profit의 [{value}], 오래된 순, 마지막 분기 끝 날짜를 period_end) → `--put-tv <산업> <파일>`.
2. 아시아 종목의 가이던스·재고가 비면 `py radar/industry_quarter.py --broker <산업>` — 국내 증권사 리포트를 인용한 기사 제목(Google News 한국판)만 나온다.
   - 원천 사이트(네이버 금융 리서치·한경 컨센서스)는 robots.txt가 막아 쓰지 않는다.
   - 제목에서 확인되는 요지만 Chiip 말로 `[{id, guide_note, inventory_note, broker_src, layer}]`에 적고 `--put-broker <산업> <파일>`.
   - 요지 없이 숫자를 지어내지 않는다. 한국 상장사는 수치 가이던스를 내지 않는 게 보통이라 "회사 수치 가이던스 없음(국내 관행)"을 먼저 적는다. 2차 인용 C등급.
3. `py radar/industry_quarter.py --collected` — 그날 수집 표시.

## phase: write — `ready` 산업마다(한 회차에 1개)
1. 장부 확인: `py -c "import sys;sys.path.insert(0,'scripts/industry');sys.path.insert(0,'radar');import quarter_frame as Q;print(Q.member_rows('<분기>','<산업>'))"`. 숫자는 장부 계산값만 쓴다.
1-0. **분기 혼합 점검(2026-11-12 회차에서 발견)**: 장부 `period`는 `sync_view.qlabel`(끝 달 기준)이라 7월 말·8월 초에 끝나는 회계 분기(NVIDIA·Broadcom·Marvell 등)를 3분기로 적는다. 석 달 중 두 달이 든 분기(`industry_segments.cal_quarter`)로는 2분기다. 회원 끝 날짜를 Fiscal.ai로 확인하고, 달력 분기가 다른 회원이 산업 매출의 20%를 넘으면 쓰지 않는다. `--done` 없이 마스터 결정을 기다린다(다른 세대의 분기를 한 결산에 합치지 않는다).
1-1. **세그먼트 장부(겸업 회사는 사업부만 — 마스터 지시 2026-11-08, ADR-020)**: 산업이 `config/industry_segments.yaml` industry_pools에 있으면
   `py radar/industry_segments.py --plan <분기> <산업>` → 회원마다 Fiscal.ai `company_segments_and_kpis`(지표명은 설정 fiscal 칸)·회사 IR 제품별 비중·TrendForce 공급사 순위 보도자료로
   `[{pool, id, period_end, currency, seg_rev, seg_rev_prev_q, seg_rev_prev_y, company_rev, grade, method, source, vol_chg, price_chg, note}]`를 만들어 `--put <분기> <파일>`.
   근거 등급 A 공시·B IR·C 제3자·E 브리지 추정(방법 필수)·U 미공시(합산 제외). 사업부 매출을 모르면 U로 둔다 — 회사 전체 매출로 채우지 않는다.
   풀이 없는 산업이라도 겸업 회사(사업부 비중 70% 미만)가 끼면 풀을 먼저 정의한다.
2. 글 datapack `knowledge/models/industries/quarterly/<분기>/<산업>/datapack.json`(형식은 scripts/industry/quarter_frame.py·scripts/industry/logic.py 맨 위, 본보기 2026Q3/nand-storage).
   - **logic 블록(IB 사고 논리, config/industry_logic.yaml)**: 한 문장 결론·지난 판단 대비 → 핵심 논쟁 3개(시장 견해+출처 ↔ Chiip 견해 ↔ 왜 다른가 ↔ 판가름 신호 날짜·지표·문턱 ↔ 확률)
     → 동인 분해(물량 × 가격, ref로 회사 사업부와 대조) → 가격 내포 기대(시장이 이미 가정한 숫자) → 시나리오 3개(확률 합 1) → 사이클 지표 3개(선행·동행·후행) → 이익 풀 → 인과 사슬(고리마다 증거 유형).
   - 서술(narrative): 무엇이 바뀌었나 → 왜 → 누가 유리해졌나 → 사이클 → 반대 검증 → 반증 조건. 숫자는 장부 값만.
   - 사업군 2~4개마다 pool·market(다음 분기 컨센서스 내포 성장 등, %p)·expected·confidence. 확신도는 근거만큼만. 겸업 회사의 전사 컨센서스를 사업군 시장 기대로 쓰지 않는다(전업 회사 값이나 사업부 가이던스).
   - **시각물(2026-11-22 마스터 지시 "Chiip Industry 11·22 잘 만들었는데, 시각물이 부족하다. 시각물을 많이 만들어 가독성을 높여라")**: 조립기가 데이터팩의 구조화 숫자(segments·scenarios·estimates·revisions·valuation_history·drivers·market_size·checkpoints)로 그래프를 자동으로 그린다(`scripts/industry/auto_charts.py`). 그 위에 datapack `tiles`(머리 수치 4~5개 — 리포트의 가장 중요한 숫자) 와 `charts`(본문 숫자로 그린 그래프 6개 이상 — 주가 2주 변화·가격·현물 지표 전후·마진 전후·수요·공급 증가율·민감도·수급 등)를 직접 적는다. `charts` 형식은 report_html 차트 그대로에 `"after": "<그 표 제목 앞부분>"`(그 표 뒤에) 또는 `"gallery": true`(한눈에 보기, 3~4개). 새 숫자를 만들지 않고 본문·표에 있는 값만, 제목에 데이터 제공처 이름을 넣지 않는다(렌더가 지운다). 렌더가 '[시각물 부족]'을 찍으면(그래프 8개 미만·타일 없음) 채우고 다시 조립한다. 본보기 knowledge/models/industries/weekly/2026-W47-dram-hbm.
3. `py scripts/industry/quarter_frame.py <분기> <산업> --predictions` → `py scripts/industry/industry_html.py outputs/industry/<날짜>_quarterly-<산업>-<분기>.json`.
4. 게시: `_artifact.html`을 claude.ai 비공개 Artifact로. 노션 Industry → '분기 결산' 아래 리포트 페이지(요약 + 링크).
   `py scripts/industry/tg_feed.py <json> --artifact <url> --notion <url> --send`(마스터 개인 봇만).
5. `py radar/industry_quarter.py --done <산업>`.

## 분기 말(3·6·9·12월 말) — 기대 얼리기
`py scripts/fiscal/estimates.py --code --days 60`을 돌려 산업 구성 종목의 발표 전 추정을 동결한다(서프라이즈·리비전의 기준). 동결이 없으면 스코어카드에 '기대 동결 없음'.
금지: 매매·비중·금액 지시, D:\local-only 읽기, 유료 리포트·IB 문장 복제(요지·출처만), 공개 채널 게시.
- **노션 IB 자료**(2026-11-08 마스터 지시): datapack을 쓰기 전 `py radar/notion_library.py --industry <산업 키>` — '요지 작성 필요'는 원문을 읽고 자기 말 요지를 `--digest <id> <파일>`로 저장한 뒤, 그 판단·숫자를 수요·시장 규모·반대 검증 절에 반영한다. 조립기가 요지 없는 자료를 만나면 멈춘다.

- **데이터 허브**(2026-11-11 마스터 지시): 판단 전에 종목은 `py scripts/tenbagger/gather.py <회사 id> --reuse`, 시장·산업은 `py scripts/tenbagger/gather.py --market --reuse`로 모든 파이프라인 출력을 먼저 본다(`docs/channels/data.md` 데이터 허브). 판단을 바꾸는 줄만 근거로 쓴다.

- **Fiscal.ai·TradingView 균형**(2026-11-15 마스터 지시 "TradingView만 많이 참조했던데 Fiscal.ai도 참조해라" → "Fiscal.ai를 먼저 가져오는 게 아니라 TradingView와 균형 있게 써라"): 비교 기업(comps)은 종목마다 두 원천을 함께 받아 대조한다 — Fiscal.ai `scripts/fiscal/templates/industry_comps.js`(execute_code, 3곳씩)와 TradingView `mcp-tv-get-symbol-data-batch`(market_cap_basic·total_revenue_ttm·total_revenue_yoy_growth_ttm·enterprise_value_current 등). 두 값이 10% 넘게 다르면 기준(회계 기간·통화·희석 주식·조정 여부)을 확인해 메모에 적고, 출처 칸에 두 원천을 모두 쓴다(예: 'Fiscal.ai·TradingView 2026-11-15'). 한쪽에 없는 종목만 `fiscal: "미수록"` 또는 `tv: "미수록"`. 주가 수익률·스크리너는 TradingView, 사업부(세그먼트)·컨센서스 분산은 Fiscal.ai가 강하다 — 강한 쪽을 쓰되 다른 쪽으로 검산한다. 조립기(`scripts/industry/logic.py`)가 한 원천만 쓴 comps를 멈춘다.
