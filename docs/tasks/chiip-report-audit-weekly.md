# Chiip Proviser — 주간 리포트 점검 (일요일 10:00)

마스터 지시 2026-11-22: "Proviser가 리포트를 업데이트하는 건 1주일에 한 번씩만 하라. 일요일 오전 10시에 한 주 동안 발행한 리포트 전부를 점검해 수치가 잘못된 부분을 점검하도록 하라."
일일 Proviser(23:00, `docs/tasks/chiip-proviser.md`)는 리포트를 점검·수정하지 않는다. 리포트를 고치는 것은 이 회차뿐이다.

1. 대상: `py scripts/proviser/report_audit.py --week --write` — 오늘(일요일)까지 7일(월~일) 동안 발행한 Analysis(텐배거) 리포트 전부. 같은 종목을 다시 쓴 경우 마지막 것만. 주기 밖 회차(`knowledge/models/tenbagger/off_cycle.csv`)는 뺀다. 결과 `docs/proviser/reports/<YYYYMMDD>_week.md`. **주 10건 상한**(2026-11-22 마스터 지시 "토큰 사용량이 크니 10개로 제한을 둬라"): 대상이 10건을 넘으면 스크립트가 발행 전 점검(`scripts/tenbagger/prepublish_check.py`) 실패가 많은 순, 같으면 최근 발행 순으로 10건만 고른다. 빠진 종목은 출력의 '이번 주 제외'에 나오고 일요일 텔레그램에 한 줄로 적는다. 상한은 `config/proviser.yaml` reports.week_max.
2. 점검의 중심은 **수치**다. 리포트마다 머리 타일(주가·시가총액·업사이드·목표주가·멀티플·가이던스)·Chiip View·한 장 요약·핵심 표의 숫자를 1차 출처(8-K EX-99.1·10-Q·회사 IR·Fiscal.ai 원자료 auditUrl)와 datapack으로 다시 대조한다 — 숫자마다 출처·일치 여부. 단위(£·$·¥·₩, B·M·펜스)·기간(분기·반기·TTM)·계산(비율·합계·증감률)도 확인한다. 과정·결론·반증은 `docs/tasks/chiip-proviser.md` 6-3 c의 기준으로 함께 본다.
3. 최종 점수: `py scripts/proviser/report_audit.py --week --final <id> <사실> <과정> <결론> <정량> <반증> fixes=<정정 수> --write`(행 날짜는 그 리포트 발행일).
4. 고친다(틀렸을 때만): `docs/tasks/chiip-proviser.md` 6-3 e 절차 그대로 — 리포트 JSON·`corrections`·필요하면 datapack → `v2_to_report.py --merge` → `report_html.py` → 렌더 확인 → '정정 기록 — Chiip Proviser HH:MM' → Artifact 같은 주소 재게시 → 정정 리포트만 텔레그램 '[수정판 — Proviser 정정 n건 …]' 1통(정정이 없는 리포트는 보내지 않는다). 목표주가·등급은 규칙 엔진이 다시 계산한 값만 쓴다. **이미지는 다시 그리지 않는다**(2026-11-22 마스터 지시 "Proviser로 Analysis Report를 점검할 때 이미지는 두 번 생성하지 않도록 하라") — 그림을 다시 묶어야 하면 `product_images.py ensure <id> --no-regen`(있는 그림만 쓰고 없으면 그리지 않는다, BOM 이름표는 렌더러가 고친 BOM으로 붙인다). 훅 `.claude/hooks/image_regen_guard.py`가 이 회차·일일 Proviser의 `--no-regen` 없는 생성 명령을 거부한다.
5. 글(맞춤법·오타·가독성) 수정도 이 회차에서 함께 — `py scripts/proviser/text_lint.py <리포트 md>` 후보를 6-4 b 기준으로 판단, 숫자·판단·인용은 바꾸지 않는다.
6. 같은 수치 오류가 두 리포트 이상에서 나오면 그 원인을 Analysis 지시서·엔진으로 올린다(`docs/proviser/chiip-tenbagger.md` 보강 지시) — 다음 주 리포트에서 반복되지 않게.
7. 끝에 텔레그램 1통(레벨 'PROVISER'): 점검 n건 · 정정 n건(종목·무엇을 전 → 후) · 반복 오류와 올린 보강. 정정이 0이면 한 줄.
7-1. **주가 반응을 다시 읽을 때 TradingView를 쓰지 않는다**(2026-11-22 마스터 지시 "Provisor로 Analysis Report의 주가 반응을 Revised할 때는 TradingView를 이용하지 마라"). 순서: 그 종목 `knowledge/models/companies/<id>/ohlcv.csv` → 모자라면 `py radar/market_data.py history <심볼>`(Tiingo·Twelve Data·EODHD) → 미국 외는 Fiscal.ai `company_stock_prices`. 훅(`config/tv_budget.yaml` deny_tasks)이 이 회차의 TradingView 호출을 거부한다. 반응일은 8-K 접수 시각(장전·장후)으로 정한다.
8. 금지: D:\local-only 읽기, 이번 주 밖 리포트 수정, 목표주가·등급을 손으로 바꾸기, 매매·비중 표현.
