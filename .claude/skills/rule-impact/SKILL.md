---
name: rule-impact
description: 규정 원문에서 대상 품목 코드(ECCN·HTS)·예외·시행일을 추출하고 config/us_gov/code_map.yaml로 T0 노출을 계산한다. 코드는 반드시 현행 원문으로 확인한다.
argument-hint: "[문서 번호]"
---

# rule-impact — 규정 영향 (§13.5⑤)
1. 규정 원문(Federal Register·eCFR)에서 영향 코드·정의·예외(라이선스 예외·de minimis 등)·시행일·유예를 표로 추출(위치 인용).
2. `code_map.yaml` 갱신: 코드·설명·제품·T0 노출·`source_rule`·`verified: true`. **기억에 의존한 코드 기재 금지.**
3. 노출 계산: 기업별 노출 경로(제품·지역 매출·생산 거점), 규모(근거 있는 범위), 불확실성.
4. 정책 영향 카드 `policy` 블록(§13.7) 작성.
