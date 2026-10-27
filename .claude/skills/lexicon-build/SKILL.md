---
name: lexicon-build
description: T0 기업의 다국어 실체 사전(config/lexicon/)을 공식 자료(사업보고서 종속회사 목록·회사 영문/중문/일문 표기·공개 코드명·부품번호 체계)로 생성·갱신하고 오탐 규칙을 작성한다.
argument-hint: "[기업 id]"
---

# lexicon-build — 다국어 실체 사전 (§11.2)
1. DART 최근 사업보고서 '연결대상 종속회사 현황'에서 법인명(국문·영문) → `legal_entities`.
2. 회사 공식 영문·중문·일문 사이트·IR 자료에서 표기 → `names`(ko/en/zh_hans/zh_hant/ja). 구 사명 포함(예: 일진머티리얼즈).
3. 사업장 → `sites`(`config/talent/sites.yaml`과 동기화).
4. 코드명·부품번호 접두어는 **공식 확인된 것만**(상표 출원·공식 발표·데이터시트).
5. `euphemisms`: 상대방이 쓰는 익명 표현 후보(가설).
6. `negative_context`: 동명이인·계열사 오탐 규칙.
7. `draft: true` 유지, 변경 내역을 마스터에게 보고. 각 항목에 근거 source_id를 주석으로.
