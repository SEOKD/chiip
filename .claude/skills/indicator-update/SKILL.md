---
name: indicator-update
description: 산업 지표(수출 통계·대만 월매출·장비 통계·메모리 가격 등)가 발표되면 indicators.csv를 갱신하고 서프라이즈를 판정해 연결 테제 영향을 적는다.
argument-hint: "[지표 id]"
---

# indicator-update — 산업 지표 갱신 (§5.14)

## 절차
1. 공식 원천에서 최신 값 확인(`source-ingest` 등록, doc_type 통계).
2. `knowledge/models/indicators.csv` 해당 행 갱신: `last_period,last_value,prior_value,yoy,mom,updated`. 단위·기준(달러/원, 잠정/확정) 명시.
3. **서프라이즈 판정**: 직전 추세·계절성·사전 기대(있으면) 대비 위/아래/부합. `surprise_note`에 1줄.
4. `linked_theses`의 테제 고리별 영향(강화·약화·무관).
5. 거울 매트릭스(`config/mirror_matrix.yaml`) 대상이면 해당 T0 기업 실적 동인에 대한 **사전 신호 카드**(`mirror-check`)로 넘긴다.

## 흔한 실수
잠정치와 확정치 혼용, 달력월·영업일 수 차이 무시, 환율 영향 미분리.
