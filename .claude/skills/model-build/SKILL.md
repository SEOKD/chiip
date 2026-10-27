---
name: model-build
description: 동인 기반 실적 모델을 만든다: 사업부별 물량×ASP, 가동률·원가 → 매출·이익·현금흐름. 입력은 CSV, 계산은 scripts/model_calc.py(수식 로직은 스크립트에 두고 숫자는 근거 id와 함께).
argument-hint: "[기업 id]"
---

# model-build — 동인 기반 실적 모델 (§7.4)
**invest 모드 경계**: `D:\local-only`와 F2~F4 필드 인텔 사용 금지, `public_corroborated: true` 주장과 F1만. 출력 하단에 `공개 자료 기반 분석이며 투자 권유가 아님`. 매수·매도 권유·개인 맞춤 투자 조언 금지(훅 public-guard가 강제).

## 파일
`knowledge/models/companies/<entity>/drivers.csv` — 열: `period,segment,driver,value,unit,basis,evidence_ids,note`
- driver 예: `volume`(출하량), `asp`(평균판매가), `cogs_per_unit`(단위원가), `opex`(판관비), `capex`, `da`(감가상각), `tax_rate`
- basis: 공시|가이던스|컨센서스|자체추정 — 자체추정은 가정을 note에 적는다.
## 절차
1. 양식 `knowledge/models/companies/_template/drivers.csv` 복사.
2. 과거 분기는 공시값(source_id), 미래는 가정(시나리오별 별도 열 대신 `scenario` 접미: `asp@bull`).
3. `py scripts/model_calc.py <entity>` → `outputs.csv`(segment별 매출·매출총이익·영업이익, 전사 합계, 단순 FCF).
4. 단위 일관성: 통화·백만 단위·기간(회계연도/분기) 명시. `check_units` 경고 확인.
5. 과거 분기 재현 오차(모델 vs 공시)를 표로 — 오차가 크면 동인 정의를 고친다.
