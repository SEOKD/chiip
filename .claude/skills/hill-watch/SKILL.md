---
name: hill-watch
description: 미국 의회 법안·청문회·증언문에서 반도체·AI 하드웨어·수출통제·관세·데이터센터 관련 내용을 추출하고 입법 단계를 추적한다. CONGRESS_API_KEY(api.data.gov) 필요. (6단계)
argument-hint: "[법안 번호 또는 주제]"
---

# hill-watch — 의회 추적 (§13.2)
1. Congress.gov·GovInfo API(키 필요)로 법안 상태·위원회·청문회 증인 명단·증언문.
2. 입법 단계(§13.6): 발의 → 위원회 → 본회의 통과 → 양원 통과 → 서명 → 시행. **발의 = 시행 금지.**
3. 증언문에서 업계 인사의 사업 데이터·입장 요약(위치 인용).
4. `knowledge/policy/policy_events.csv` 행, 일정은 calendar.csv.
