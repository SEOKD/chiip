---
name: fedreg-watch
description: 미국 관보(정식 게재·사전 공람)·백악관·BIS 문서 항목을 판정해 정책 단계와 T0 노출을 정리한다. 레이더가 수집한 src-fedreg·src-fedreg-pi 항목에 쓴다.
argument-hint: "[item_id 또는 문서 번호]"
---

# fedreg-watch — 관보 판정 (§13.2)
1. 문서 원문(html_url)을 열어: 기관, 문서 유형(규칙안·최종 규칙·고시·대통령 문서), 대상 품목·코드, 시행일, 의견 마감일.
2. **정책 단계**(§13.6)로 기록: 조사 개시 → 규칙안 → 의견 수렴 → 최종 규칙 → 시행일 → 유예·예외. 사전 공람이면 "정식 게재 예정일 ○○".
3. T0 노출: `rule-impact`로 넘기거나 간단하면 직접(코드 → 제품 → 기업, `config/us_gov/code_map.yaml`).
4. `knowledge/policy/policy_events.csv` 행 추가, 일정(의견 마감·시행일)을 `knowledge/calendar.csv`에.
5. 중요하면 `policy-flash`.
