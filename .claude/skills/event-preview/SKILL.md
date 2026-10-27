---
name: event-preview
description: 일정(calendar.csv)에 있는 이벤트의 사전 기대 노트. 컨센서스·회사 가이던스·치입 판단, 그리고 '무엇이 나오면 놀랄 것인가'를 미리 적는다. 실적 발표·학회·제품 행사 2~5일 전에 쓴다.
argument-hint: "[날짜 또는 이벤트]"
---

# event-preview — 이벤트 사전 노트 (§7.2, §14 이벤트 플레이북)

## 절차
1. `knowledge/calendar.csv`에서 대상 이벤트를 찾는다.
2. 비교 기준 수집: 직전 분기 가이던스·콜 발언(주장 id), 공개된 컨센서스(출처 명시, 없으면 "미확인"), 관련 테제.
3. 체크리스트 작성:
   | 항목 | 기대(근거) | 놀람 기준(상방) | 놀람 기준(하방) |
4. **"무엇이 나오면 놀랄 것인가"** 3개 — 측정 가능한 문장으로.
5. 각 테제의 어느 고리가 이 이벤트로 검증되는지.
6. 측정 가능한 예측이 있으면 `prediction-log`(6단계) 후보로 표시.

## 저장
`outputs/brief/YYYYMMDD_preview_<event>.md` 그리고 calendar.csv의 `expectation_note_ref`에 경로 기록.
이벤트 후 `earnings-delta`가 이 노트를 비교 기준으로 쓴다.
