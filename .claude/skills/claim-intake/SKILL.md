---
name: claim-intake
description: 등록된 원천에서 주장(claim)을 뽑아 knowledge/claims/에 저장한다. 사실·가이던스·추정 등 지식 레이어에 들어가는 모든 문장은 이 절차를 거친다. 레이더 카드·역방향 신호(S3 이상)를 지식으로 승격할 때도 쓴다.
argument-hint: "[source_id 또는 카드/신호 id]"
---

# claim-intake — 주장 등록

## 목적
저장 단위는 보고서가 아니라 주장이다(P1). 출처·위치·발언자·공개일이 없는 문장은 저장하지 않는다(P2).

## 입력
`sources/index.yaml`에 등록된 source_id. (등록 전이면 먼저 `source-ingest`.)
레이더 카드(`R-…`)·역방향 신호(`SIG-…`, S3 이상만)도 입력 가능.

## 절차
1. **분석 단위 6질문** — 각 주장마다 답한다. 답 못 하면 `미확인`.
   1. 무엇: 어떤 제품·기술·사건인가 (세대·사양까지)
   2. 어디: 어느 기업·사업부·사업장·고객
   3. 기능: 그것이 시스템에서 하는 일
   4. 연결: 어느 실적 동인(물량·함량·가격·점유율·제조비용·시점)과 연결되나
   5. 대체: 대안 기술·대체 공급사는 무엇인가
   6. 담당: 누가 설계·제조·조립·검사·판매하나 (역할 분리)
2. **유형 판정** (`claim_type`): 확정사실 / 가이던스(회사 전망) / 추정(제3자·IB) / 채널체크 / 자체추론(치입 계산) / 필드인텔(F1만 직접, 그 외는 `FI-` 추상 id).
3. **novelty 판정** — `knowledge/claims/`에서 같은 subject(company·product·customer·period)를 검색:
   | 상황 | novelty |
   |---|---|
   | 처음 나온 내용 | 신규 |
   | 기존 주장의 수치·시점이 바뀜 | 수정 (`supersedes`에 기존 id) |
   | 같은 내용을 독립 출처가 확인 | 추가검증 (기존 주장 evidence에 추가하는 것도 고려) |
   | 같은 원출처 재인용 | 반복 — **새 주장 만들지 않음** |
   | 같은 사실의 새로운 해석 | 재해석 |
   | 출처끼리 충돌 | 미확정 |
4. **상용화 세 축**: `status.manufacturing / customer / business`를 각각 그 축의 증거로만 채운다. 샘플 출하 → customer: 샘플 (manufacturing을 출하로 채우지 않음).
5. **금지표 검사** (CLAUDE.md): 샘플→양산, MOU→매출, 투자 발표→공급 증가, 채용→증설, 규칙안→시행 등을 문장에 담지 않았는지.
6. **반증 조건·다음 확인**: `falsifier`(무엇이 나오면 이 주장이 틀리나), `next_check`(다음 확인 사건·날짜).
7. **id·저장**: `py scripts/chiip_ids.py claim` → `knowledge/claims/YYYY/MM/<id>.yaml` (양식: `docs/templates/claim.yaml`).
8. **검증**: `py scripts/validate_claims.py <파일>` 통과할 때까지 수정. `py scripts/check_units.py <파일>` 경고 확인.
9. `public_corroborated`: 공개 자료로 확인됐으면 true. 필드 인텔만이 근거면 false.
10. `user_confirmed`: 항상 false로 저장. 마스터가 확인하면 true.

## 출력
`[주장 등록] C-… (유형/novelty/신뢰도) 한 줄 요약` 목록 + 등록하지 않은 문장과 이유.

## 완료 기준
validate 통과, 중복 없음, 모든 evidence에 locator(쪽·분·문단)와 자기 말 요지.

## 흔한 실수
- 한 문장에 여러 주장 → 쪼갠다(물량 주장과 가격 주장은 별개).
- 원문 장문 인용 → `gist_ko`는 자기 말 요지 2문장 이내.
- 기간 표기 누락(`period`) → 분기·반기·연도 명시, 회계연도/달력연도 구분.
- AI(치입)의 과거 답변을 근거로 사용 → 금지(P11). 원천을 다시 찾는다.
