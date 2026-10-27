---
name: impact-card
description: P0·P1 레이더 카드의 영향 판정을 완성한다. 1차 출처 확인 → novelty → 1차 영향(실적 동인·방향·규모·시점) → supply_relations 경로를 따라 2차 영향 전파 → 시장 맥락 → 엣지 해석(가설) → 기사 각도. 카드 id나 경로를 받는다.
argument-hint: "[radar/cards/…/R-….yaml 또는 카드 id]"
---

# impact-card — 영향 판정 카드 완성 (BUILD_PROMPT §5.13, §10.6)

## 절차
1. **카드 열기**: `$ARGUMENTS`가 id면 `radar/cards/**/<id>.yaml`을 찾는다. 원 항목은 `radar/inbox/**`에서 item_ids로.
2. **1차 출처 확인**: 공시(DART·SEC)·회사 보도자료가 있으면 링크를 찾아 `primary_source_confirmed: true`. 보도만 있으면 false 유지, open_questions에 "1차 출처 확인".
3. **novelty**: `knowledge/claims/`, `knowledge/theses/`와 비교 → 신규/수정/반복. linked_claims·linked_theses 기록.
4. **1차 영향** (`first_order`): 기업별 driver(물량|함량|가격|점유율|제조비용|시점), line_item, direction(상향|하향|중립|불명), magnitude(무시|소|중|대 — **기준을 rationale에 명시**: 예 "연매출 대비 1% 미만=소"), timing, rationale.
5. **2차 영향** (`second_order`): `knowledge/models/supply_relations.csv`에서 해당 기업의 공급사·고객·경쟁사 경로. 관계가 `후보`·`미확인`이면 confidence: 낮음. 경로 문자열 예 `co-skhynix → (TC본더 공급) → co-hanmisemi`. 관계 데이터가 없으면 비워 두고 open_questions에 "공급관계 미구축".
6. **시장 맥락**: 주가 반응·컨센서스는 확인 가능한 공개 자료가 있을 때만. 없으면 "미확인", `priced_in: 불명`. "시장이 간과" 표현 금지(금지표).
7. **엣지 해석** (`edge_angle`): 시장과 다르게 볼 수 있는 해석 1~2문장, **"(가설)"** 표시. 근거: 테제·엔지니어 관점. 로컬 세션이면 `field_intel_index.csv`의 관련 FI 포인터와 대조해 `field_intel_check`만 기록(원문 불필요, 내용 출력 금지).
8. **기사 각도** (`article_angle`): 야마 후보 1문장.
9. **금지표 점검**: 협력→매출, 투자→공급, 샘플→양산 등.
10. `verification: 1차판정` 유지(사람 검토 후 검증완료).
11. P0면 `flash-note`를 이어서 작성.

## 출력
갱신된 카드 파일 + 화면 요약 5줄(무엇/1차 영향/2차 영향/시장/야마).

## 흔한 실수
- magnitude 기준 없이 "대".
- 2차 영향을 공급 관계 확인 없이 추정해 confidence 높음.
- 엠바고·local-only 정보를 카드에 기록.
