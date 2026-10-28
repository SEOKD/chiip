# ADR-008 밸류에이션 시스템 (2026-10-28)

## 상태
채택(마스터 지시 2026-10-28: "세미애널리시스처럼 뉴스와 리서치 병행 — 멀티플 프리미엄·EPS 리비전·내러티브·가격 반영도를 다루는 밸류에이션 시스템", "아키텍처에 코드와 바이브로, 아침/저녁 브리핑에 포함"). 데이터 요금제는 미정.

## 결정
1. 6층 구조(L0 수집 → L1 리비전 → L2 멀티플 → L3 내포 기대 → L4 내러티브 → L5 반영도). 숫자는 코드(`radar/markets/valuation_data.py`, `scripts/valuation/engine.py`), 해석·시나리오·내러티브 단계는 모델(스킬 `valuation-card`).
2. IB 방법은 공개 보도로 확인한 원리만 차용(§14). Citi는 공개 확인 실패 → 미확인으로 둔다.
3. 데이터 원천은 교체 가능하게: EODHD 펀더멘털(추정치·리비전 — 'Fundamentals' $59.99 또는 'ALL-IN-ONE' $99.99 필요), EOD 가격, 수동 컨센서스 CSV. 데모 키로 필드 구조 확인(FY0·FY1 추정치, 7·30·60·90일 전 EPS, 상·하향 건수, 서프라이즈) — **FY+2 없음**, 한국·일본 추정치 채움 여부 미확인.
4. 내러티브 강도는 레이더 수집 항목의 키워드 일치 건수(결정론). 단계 판정은 모델.
5. 반영도는 방향 예측이 아니라 "기대의 높이". 목표주가·투자의견은 내지 않는다.
6. 아침·저녁 브리프에 '■ 밸류에이션 레이더' 절(데이터 없으면 내러티브 강도만 + "가격·추정치 미수집").

## 출처 (공개 2차 보도)
- MS 엔비디아: https://finance.yahoo.com/markets/stocks/articles/morgan-stanley-resets-nvidia-stock-154922400.html
- MS 마이크론: https://www.tradingview.com/news/gurufocus:c9d952f14094b:0-micron-stock-pops-as-morgan-stanley-raises-price-target-to-450/
- GS 마이크론: https://rallies.ai/news/goldman-raises-micron-price-target-to-900-keeps-neutral-ahead-of-earnings
- GS SK하이닉스·메모리 기준 전환: https://www.itiger.com/news/1105910250
- JPM SK하이닉스: https://www.itiger.com/news/1195401286
- TD Cowen 마이크론: https://finviz.com/news/286249/micron-mu-seen-benefiting-from-prolonged-memory-cycle-td-cowen-says
- GS AI 4단계: https://blog.moneyfarm.com/en/?p=17061
- GS 리비전 팩터: https://www.tickmill.com/blog/institutional-insights-goldman-sachs-us-weekly-kickstart-18526
- MS 소프트웨어 성장 조정 EV/S: https://www.itiger.com/news/1112322021
- Mauboussin 역DCF: https://www.michaelmauboussin.com/s/EIexcerpt.pdf
- Damodaran: https://pages.stern.nyu.edu/~adamodar/pdfiles/country/narrative&numbersrealshort2025.pdf
- EODHD 요금: https://eodhd.com/pricing

## 남은 결정 (마스터)
- 데이터 요금제(올인원 $99.99 / 펀더멘털 $59.99 / 유료 추가 없이 수동 입력)
- 할인율·장기 P/E 가정, 유니버스·하위 섹터 분류, 내러티브 노출 가중치(모두 초안)
