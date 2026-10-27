---
name: prediction-log
description: 측정 가능한 예측을 predictions.csv에 등록하고 만기에 판정한다. 사후 수정 금지(정정은 새 행).
argument-hint: "[등록|판정] [내용]"
---

# prediction-log — 예측 원장 (§5.9)
## 등록
- 측정 가능한 문장만: 지표·목표값·기한·확률(0~1)·근거(주장·테제 id).
- 예: `SK하이닉스 2027Q1 HBM 매출 비중 ≥ X% (회사 공시 기준), 기한 2027-04-30, 확률 0.6`
- `knowledge/predictions.csv`에 새 행. `pred_id`는 `P-YYYYMMDD-NN`.
## 판정
- `py scripts/score_predictions.py`가 만기 도래 목록을 준다. 1차 출처로 확인해 `resolved_on`, `outcome`(1/0), `notes`(근거 source_id).
- 기존 행의 statement·probability는 고치지 않는다. 정정이 필요하면 새 행 + notes에 "P-… 정정".
## 분기 리포트
- 브라이어 점수·적중률·필드 인텔 선행성(`score_field_intel.py`)을 묶어 트랙레코드로.
