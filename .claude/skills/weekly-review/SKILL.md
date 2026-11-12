---
name: weekly-review
description: '주간 리뷰(토요일 오전): 글로벌 증시 주간 상승률(Dean''s Ticker 형식), 테제별 변화, 지표 변화, 예측 진행, 다음 주 카탈리스트, 레이더·역방향·필드 인텔 성능. outputs/brief/에 저장하고 claude.ai 비공개 Artifact로 공유.'
argument-hint: "[주차 YYYY-Www]"
---

# weekly-review — 주간 리뷰 (2026-10-31 재설계)

마스터 평가: 가독성·품질·구성 모두 3/10 이하. 진단은 '시장 보고서가 아니라 운영 장부'였다. 독자의 질문은 하나다 — **이번 주 무엇이 바뀌었고 다음 주 무엇을 보나.** 휴대폰으로 3분 안에 끝나야 한다.

## 규칙 (마스터 지시 2026-10-31)
- 데이터는 Fiscal.ai를 쓴다. 등락률 검증, 섹터 온도, 컨센서스·가이던스, 실적 일정 모두. Fiscal에 없는 스크리닝과 아시아 등락률만 TradingView.
- 판정할 수 없는 항목은 보고서에서 뺀다. 빈칸·'미확인'·'평가 불가'를 쓰지 않는다.
- 본론만 쓴다. 작업 과정에서 생긴 일(원천 장애, 파일 상태, 재계산, 지시 번호)은 쓰지 않는다.
- 대만·홍콩 회사는 한국어 표기로 쓴다.
- 구성은 `scripts/weekly/render.py`가 고정한다. 모델은 글만 쓴다. 관문(`config/weekly_review.yaml`)을 넘으면 렌더가 멈추므로 글을 고친다.

## 절차
1. **주간 상승률**: `config/weekly_movers.yaml` tradingview 설정대로 `mcp-tv-run-screener`를 지역별로 `sort_by: "change|1W"`로 돌린다. 개수는 US 20, US(<$10B)·Europe·Japan·Korea·Taiwan·Hong Kong 각 10. 미국·유럽 상위 종목은 Fiscal.ai `company_stock_prices`로 직전 금요일 종가 대비를 대조한다(유럽 키는 XCSE_·XOSL_·XSTO_·XLON_·XETR_·XPAR_·XSWX_). 우선주·같은 회사 중복 상장·해외 주식 코드는 뺀다. 사업을 확인하지 못한 종목은 찾아보고, 그래도 모르면 뺀다.
2. 행마다 `{region, rank, pct_change, name_ko, desc_ko, theme, ticker, as_of}`를 JSON 목록으로 쓰고 `py radar/markets/weekly_movers.py --put <파일> <YYYY-Www>`. name_ko는 한국 통용 표기, desc_ko는 2~10자 사업, theme은 바이오·의료 / 반도체·부품 / 사이버보안·SW / 전력·에너지 / 방산·우주 / 금융·서비스 / 소비재 / 산업·소재 중 하나.
3. **글로벌 지수**: S&P 500, 나스닥 100, 필라델피아 반도체, 러셀 2000, 유로 스톡스 50, FTSE 100, 닛케이 225, 코스피, 코스닥, 항셍 — `mcp-tv-get-symbol-data-batch`의 `change|1W`.
4. **이번 주 바뀐 것 3~4건**: 그 주 P0 카드·실적·공시에서 판단을 바꾸는 것만 고른다. 사실을 1차 자료로 대조한 뒤 건마다 무엇이·왜 중요한가·유리·불리·다음 확인을 한두 문장으로 쓴다. '왜 올랐나'는 1차 자료가 있을 때만 쓴다(금지표: 주가 급등 → 펀더멘털 변화).
5. **섹터 온도**: `knowledge/models/portfolio/sector_latest.json`(Fiscal.ai) 3~6행, 읽기는 한 구절.
6. **다음 주 볼 것 4~6건**: 일정 전체가 아니라 판단을 가르는 사건만. 날짜(KST)·무엇·볼 숫자(Fiscal `company_estimates`)·의미.
6-2. **AI 하드웨어 리드타임·병목**(마스터 지시 2026-11-04): 그 주에 나온 AI 밸류체인 기업의 실적 보도자료·어닝콜 전문(Fiscal.ai)·노션 IB 리포트에서 부품별 리드타임 발언을 모은다(HBM·CoWoS·기판·CCL·광 모듈·전력 반도체·변압기·개폐기·가스터빈·냉각 등 4~12개). 부품마다 `now`(이번 주 확인한 리드타임, 주)·`prev`(전주 Weekly 값, 없으면 생략)·`normal`(평시, 근거 있는 값)·`weight`(AI 서버·데이터센터 BOM 비중, 선택)·`evidence`(회사·자료 한 줄)·`n`(독립 근거 수)를 JSON `leadtime.components`에 쓰고, `read`에 병목이 어디서 어디로 옮겨 가는지 한 문장. 엔진이 압박도(지금÷평시)·병목 지수·지금 병목·늘어난 곳·풀린 곳을 계산한다. 같은 원출처 재인용은 n에 세지 않는다. 리드타임 숫자가 없으면 그 부품은 넣지 않는다.
6-3. **Earnings 알파 점검**(마스터 지시 2026-11-07 "매주 주중 어닝을 발표한 종목들을 점검하고 알파 평가 점수를 매긴 이후 6점 이상인 종목을 Watchlist에 넣고 Analysis 리포트를 적어라 … Weekly Review Report에도 관련 내용을 넣어라"). 태그 = 주차(`2026-W46`), 기간 = 그 주 월~금(KST). 설정 `config/earnings_sweep.yaml`, 계산 `scripts/discovery/earnings_sweep.py`:
   a. 미국 전수(결정론): `py scripts/discovery/earnings_sweep.py --sec <주차> <월> <금>` — EDGAR 8-K Item 2.02 전부 + SEC frames 재무.
   b. 한국·일본·대만: TradingView `mcp-tv-run-screener`를 시장마다 `earnings_release_date` ∈ [월 00:00, 토 00:00) UTC 초, 시가총액 하한(설정 fx 환산)으로 한 번은 limit 1로 불러 totalCount(발표 종목 수)를 얻고, 한 번은 `revenue_surprise_percent_fq` 내림차순 limit 20으로 받는다. 우선주는 뺀다. 행을 설정 columns만 남긴 JSON 목록으로 저장 → `--put <주차> <파일> <시장> --total <totalCount>`.
   c. `--rank <주차>` → `--targets <주차>`가 내는 미국 티커(정량 상위 150)를 `mcp-tv-get-symbol-data-batch`(50개씩, `NASDAQ:`/`NYSE:` 접두, 열은 설정 columns)로 받아 `--put <주차> <파일> america` → 다시 `--rank <주차>`.
   d. `--rank`가 낸 판단 후보(최대 25 + 이미 알파가 있는 종목)를 스킬 tenbagger-card '알파 점수' 절대로 매긴다 — 근거 URL(8-K·IR 보도자료) 필수, 판단 파일 `knowledge/models/alpha/judgments/YYYYMMDD.csv` → `py scripts/alpha/score.py --finalize`.
   e. `--finalize <주차> --floor 6` → 알파 6.0 이상을 와치리스트(added_by: earnings-sweep, alpha_floor 6)·Analysis 리포트 대기열에 넣는다. 통과 종목마다 weekly json `earnings_alpha.notes`에 왜 알파가 높은지 1차 자료로 한 줄, `earnings_alpha.read`에 이번 주 점검 한 줄. 렌더러가 'Earnings 알파 점검' 절을 만든다(점검 파일이 없으면 절을 뺀다).
6-1. **Nebius GPU 렌털료 추이**(2026-11-13 마스터 지시): 표는 렌더러가 자동으로 넣는다(`scripts/weekly/gpu_rent.py`, 변화 없어도 매주). 바뀐 GPU가 있거나 정가와 Silicon Data 지수의 괴리가 크게 움직였으면 JSON `gpu_read`에 읽기 한 문장을 쓴다.
7. **이 판단이 틀릴 조건 2~3줄**.
8. 첫 문장(headline)과 결론 3줄을 맨 마지막에 쓴다. 지수·종목 나열이 아니라 그 주의 변화 한 문장이다.
9. `outputs/brief/<YYYY-Www>_weekly.json`(구조는 `scripts/weekly/render.py` 맨 위) → `py scripts/weekly/render.py <YYYY-Www>` → .md·.html.
   **발행은 한 묶음이다. 보고서를 쓰거나 다시 쓸 때마다 끝까지 한다**(마스터 지시 2026-10-31). 시작할 때 `py scripts/weekly/publish_weekly.py pending`으로 지난 미완료부터 처리한다.
   a. Artifact 도구로 .html 게시(있으면 같은 URL 갱신) → `py scripts/weekly/publish_weekly.py artifact <주차> --url <URL>`
   b. `py scripts/weekly/publish_weekly.py notion-body <주차>` → 제목·`<주차>_notion.md`를 노션 커넥터로 `config/notion.yaml` pages.weekly 아래 하위 페이지에 올린다. `existing_page`가 있으면 새로 만들지 말고 그 페이지를 `replace_content`로 갱신한다 → `... notion <주차> --page <URL>`(실패면 `--fail "이유"`)
   c. `py scripts/weekly/publish_weekly.py send <주차>` — 마스터 개인 텔레그램으로 결론과 두 링크. 다시 쓴 판은 '수정판'으로 나간다. 같은 판은 두 번 보내지 않는다.
10. **운영 기록은 보고서 밖**: `py scripts/score_*.py` 결과, 예측 원장, 기사 소재 채택, 수집 장애, 개선 제안은 `outputs/brief/<YYYY-Www>_ops.md`에 쓴다 — Proviser가 읽는다. 예측이 그 주에 판정됐으면 그때만 보고서 '이번 주 바뀐 것'에 넣는다.

채널 게시는 마스터가 직접 한다. 리포트의 '채널용 텍스트'를 복사해 쓴다.


운영 규칙: `docs/channels/weekly.md`를 먼저 읽는다. '이번 주 바뀐 것'을 고르기 전에 `py radar/dticker.py --recent 7 --columns`로 마스터가 쓴 글을 본다(`docs/channels/dticker.md`).

노션 자료 참조(2026-11-01 마스터 지시): '이번 주 바뀐 것' 종목은 `py radar/notion_library.py --need <회사>`의 요지와 게시글을 참조한다.

**무역·PPI(마스터 지시 2026-11-02):** 그 주 새 수치가 판단을 바꿀 때 쓴다. 필요할 때 `py radar/trade_ppi.py --status`(또는 `--need <회사 id>`)로 7개 지역 세부 지표를 본다. PPI 전년비·수입처 변화가 판단을 바꿀 때만 쓰고, 나열하지 않는다. 별표는 업종 대용 지수다. 값이 없으면 '미확인'이다.

- **데이터 허브**(2026-11-11 마스터 지시): 판단 전에 종목은 `py scripts/tenbagger/gather.py <회사 id> --reuse`, 시장·산업은 `py scripts/tenbagger/gather.py --market --reuse`로 모든 파이프라인 출력을 먼저 본다(`docs/channels/data.md` 데이터 허브). 판단을 바꾸는 줄만 근거로 쓴다.
