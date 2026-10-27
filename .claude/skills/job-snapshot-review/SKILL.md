---
name: job-snapshot-review
description: 일일 채용 공고 스냅숏(radar/talent/postings/)의 신규·마감·재게시를 판정하고 직무·위치·키워드 태깅을 검수해 hiring_index.csv를 갱신한다. 채용 수집기가 돌기 시작한 뒤 매일 쓴다.
argument-hint: "[YYYY-MM-DD]"
---

# job-snapshot-review — 채용 스냅숏 검수 (§12.3)

## 절차
1. 오늘·어제 스냅숏(`radar/talent/postings/YYYY/MM/DD.jsonl`)을 비교: 신규(first_seen=오늘), 마감(어제 있고 오늘 없음 → closed_at), 재게시(content_hash 유사·제목 같음 → repost_of).
2. 태깅 검수: `function`(공정/설비/패키징·테스트/설계/소프트웨어·펌웨어/품질·신뢰성/고객 대응/구매·공급망/영업·마케팅/건설·인프라·환경안전/연구/경영지원), `location.site`(config/talent/sites.yaml), `tech_keywords`·`equipment_keywords`·`customer_keywords`(config/keywords.yaml, config/lexicon/).
3. **신규 키워드 첫 등장**: 지난 90일 스냅숏에 없던 기술·고객 키워드 → 따로 표시.
4. `knowledge/models/hiring_index.csv`에 일 단위 집계 행 추가(개인 정보 없음).
5. 신규 키워드 첫 등장·특정 사업장 급증은 `hiring-trend`(5단계) 입력으로 남긴다. **채용은 의도이지 실행이 아니다**(P21).

## 출력
`신규 n / 마감 n / 재게시 n / 첫 등장 키워드 [...]` 한 줄 + 집계 행.
