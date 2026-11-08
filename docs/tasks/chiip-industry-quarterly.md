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
3. `py scripts/industry/quarter_frame.py <분기> <산업> --predictions` → `py scripts/industry/industry_html.py outputs/industry/<날짜>_quarterly-<산업>-<분기>.json`.
4. 게시: `_artifact.html`을 claude.ai 비공개 Artifact로. 노션 Industry → '분기 결산' 아래 리포트 페이지(요약 + 링크).
   `py scripts/industry/tg_feed.py <json> --artifact <url> --notion <url> --send`(마스터 개인 봇만).
5. `py radar/industry_quarter.py --done <산업>`.

## 분기 말(3·6·9·12월 말) — 기대 얼리기
`py scripts/fiscal/estimates.py --code --days 60`을 돌려 산업 구성 종목의 발표 전 추정을 동결한다(서프라이즈·리비전의 기준). 동결이 없으면 스코어카드에 '기대 동결 없음'.
금지: 매매·비중·금액 지시, D:\local-only 읽기, 유료 리포트·IB 문장 복제(요지·출처만), 공개 채널 게시.
- **노션 IB 자료**(2026-11-08 마스터 지시): datapack을 쓰기 전 `py radar/notion_library.py --industry <산업 키>` — '요지 작성 필요'는 원문을 읽고 자기 말 요지를 `--digest <id> <파일>`로 저장한 뒤, 그 판단·숫자를 수요·시장 규모·반대 검증 절에 반영한다. 조립기가 요지 없는 자료를 만나면 멈춘다.
