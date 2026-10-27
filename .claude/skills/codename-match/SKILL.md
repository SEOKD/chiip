---
name: codename-match
description: 미국 경제개발 안건의 코드명 프로젝트('Project ○○')의 공개 속성(투자액·고용·부지·전력·용수·업종)을 누적하고 경쟁 가설 분석으로 후보 기업을 매핑한다. 매핑은 가설.
argument-hint: "[코드명]"
---

# codename-match — 코드명 프로젝트 (§13.5③)
1. `knowledge/policy/codename_projects.csv`에 속성 행 추가/갱신(출처 source_id).
2. 후보 기업 나열 → ACH 표(속성별 일치·불일치) — `euphemism-resolve`와 같은 방식.
3. `candidates`에 순위대로(`co-a;co-b`), 근거·가정 명시. **가설**(P17).
4. 실명 공개 시 `resolved_entity`·`resolved_at` 기록 + 선행성 장부.
