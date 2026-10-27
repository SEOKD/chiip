---
name: org-chart-sync
description: DART 사업·반기·분기보고서의 '임원 및 직원 등의 현황'으로 조직도(knowledge/org/)와 인력 지표(headcount.csv)를 갱신하고 보도 내용과 대조한다. 정기보고서 제출 시 쓴다.
argument-hint: "[기업 id] [보고서 source_id]"
---

# org-chart-sync — 공시 기반 조직도 (BUILD_PROMPT §12.1 T4, §12.6)

## 절차
1. 보고서를 `source-ingest`(doc_type: 공시)로 등록. DART 뷰어 링크와 해당 장 위치를 locator로.
2. **임원 현황** 표에서 성명·직위·담당 업무·등기 여부를 읽어 `knowledge/org/<company>/org_chart.md`의 표를 갱신:
   | 부문 | 사업부·조직 | 직위 | 성명 | 담당 업무 | 등기 | 근거 |
   - 공개 직책자(대표이사·사업부장·연구소장·해외 법인장·공개 발표한 기술 리더)는 `knowledge/people/`에 파일 생성·갱신(공개 직업 정보만).
   - 일반 직원은 다루지 않는다.
3. **직원 현황**: 부문별 직원 수·평균 근속·평균 급여 → `knowledge/models/headcount.csv`에 `company,period,segment,employees,avg_tenure_years,avg_pay,source_id`.
4. 직전 보고서 대비 변화(신규 임원·사라진 임원·담당 업무 변경·부문 인원 증감)를 `org_changes.csv`에.
5. 보도된 인사 내용과 다르면 차이를 적고 공시를 우선.

## 출력
변화 요약(신규·이탈·담당 변경·인원 증감) + 갱신 파일 목록.

## 흔한 실수
- 미등기 임원 누락. 담당 업무 표기를 임의로 표준화해 원 의미 훼손(원문 표기 병기).
