# 동인 기반 실적 모델 (6단계, invest 모드)
- 기업별 폴더 `<entity>/drivers.csv` (양식 `_template/drivers.csv`) → `py scripts/model_calc.py <entity>` → `<entity>/outputs.csv`
- 시나리오는 driver 이름 뒤 `@bull`, `@bear` (없으면 기본값 사용)
- 공개 자료·F1만 근거로 쓴다(local-only 금지). 결과 해석은 valuation-bridge·consensus-gap 스킬.