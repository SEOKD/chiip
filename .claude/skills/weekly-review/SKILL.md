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