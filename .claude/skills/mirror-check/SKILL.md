---
name: mirror-check
description: 거울 매트릭스 데이터(대만 월매출 등, knowledge/models/mirror_monthly.csv)가 새로 들어오면 T0 실적 동인에 대한 사전 신호 카드를 만든다. 매월 10일 전후.
argument-hint: "[YYYY-MM]"
---

# mirror-check — 거울 데이터 판정 (§11.5)
1. `mirror_monthly.csv`에서 해당 월 행과 직전 3개월·전년 동월을 읽는다.
2. T0별(`mirror_for`)로 거울 기업 그룹의 YoY·MoM을 요약. 통화(천 대만달러)·환율 영향 주의.
3. 해석은 가설: "대만 기판사 매출 급증 → 한국 기판사도 수요 호조"와 "대만사 점유율 상승(한국사엔 부정)"을 **둘 다** 적는다.
4. 사전 신호 카드(`radar/cards/`, event_type 기타, headline "거울: …", verification 1차판정) — P2 기본, 이례적 변화(±30%p 이상 등 기준 명시)면 P1.
5. `indicators.csv`의 `ind-tw-monthly-rev` 갱신.
