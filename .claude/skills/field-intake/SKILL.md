---
name: field-intake
description: 마스터의 직접 취재 정보(필드 인텔)를 받는다. 공개 등급 F1~F4 판정, Admiralty 2축 신뢰도 평가, 저장 위치 분기, 저장소에는 추상 포인터만 남기는 절차. 마스터가 "취재 메모", "필드 인텔", "들은 얘기", "엠바고 자료"를 줄 때 쓴다. 로컬 세션에서만 실행.
argument-hint: "[메모 또는 F4 포인터]"
---

# field-intake — 필드 인텔 입력

## 목적
필드 인텔은 치입의 가장 중요한 엣지다. 동시에 취재원 보호·미공개정보·엠바고 리스크가 가장 큰 정보다. 이 스킬은 **가치를 살리면서 경계를 지킨다.**

## 절대 규칙 (BUILD_PROMPT §3, §21.4)
- **F4(봉인) 원문은 받지 않는다.** 마스터가 F4 원문을 붙여 넣으면 저장·요약·인용하지 말고 즉시 이렇게 답한다:
  "F4는 원문을 받지 않습니다. 대신 ① 관련 기업·주제 태그 ② 출처 등급(A~F) ③ 정보 등급(1~6) ④ 다른 정황과 맞는지만 알려 주세요."
- F3는 취재원 식별 정보(이름·부서·연락처)를 마스터가 지운 뒤 받는다. 식별 정보가 보이면 저장 전에 지우도록 요청한다.
- 저장소(`chiip/`)의 어떤 파일에도 F2~F4 원문·수치·인용을 쓰지 않는다.
- 클라우드 루틴·GitHub Actions·claude.ai Artifact에서는 이 스킬을 실행하지 않는다.

## 절차
1. **공개 등급 판정** — 애매하면 마스터에게 묻고, 답이 없으면 **더 보수적인 등급**으로.
   | 등급 | 조건 | 저장 |
   |---|---|---|
   | F1 공개 | 마스터 기사로 보도 완료 또는 회사 공식 공개 | `source-ingest`로 등록(doc_type: 사용자보도) |
   | F2 엠바고 | 해제 시각이 지정된 자료 | `D:\local-only\embargo\<FI-id>.md` + `embargo_until` |
   | F3 보도 예정 | 취재 완료·기사화 전 | `D:\local-only\sealed\field\<FI-id>.md` |
   | F4 봉인 | 비보도·취재원 보호·배경 설명 | 원문 없음. 포인터만 |
2. **Admiralty 2축 평가**
   - 출처 신뢰도: A 완전 신뢰 · B 대체로 신뢰 · C 꽤 신뢰 · D 대체로 불신 · E 불신 · F 판단 불가
   - 정보 신뢰도: 1 타 출처로 확인 · 2 아마 사실 · 3 가능성 있음 · 4 의심 · 5 거의 불가 · 6 판단 불가
   - 같은 `source_class`의 과거 적중률(`knowledge/field_intel_index.csv`의 outcome)을 참고해 제안하고 마스터가 확정.
3. **source_class** 작성 — 사람이 아닌 직무 범주만: `A-fab-planning`, `B-package-test`, `C-equipment-vendor`, `D-customer-side`, `E-materials`, `F-conference-floor`, `G-company-official` 등. 회사명·부서명 조합으로 사람이 특정되면 더 넓은 범주로.
4. **id 발급**: `py scripts/chiip_ids.py field` → `FI-NNNN`.
5. **포인터 기록**: `knowledge/field_intel_index.csv`에 한 줄 추가
   `fi_id, entered_at(KST), disclosure_class, source_class, reliability(B2 등), entities(co-…;…), topics(키워드;…), linked_theses, corroboration(pending|corroborated|contradicted), embargo_until, f1_converted_at, publicly_confirmed_at, confirm_source_id, lead_days, outcome(pending|confirmed|refuted|unresolved)`
   - topics에는 수치·고객명 추정·원문 표현을 쓰지 않는다. 예: `hbm4;qualification` (O), `엔비디아향 12단 6월 인증` (X).
6. **대조**: 관련 테제·주장(`knowledge/claims/`, `knowledge/theses/`)과 비교해 마스터에게만 보고: 일치 / 상충 / 새로움.
7. **공개 확인 대기 등록**: 어떤 공개 흔적(공시·발표·상대방 공시·인허가)이 나오면 확인되는지 2~3개 적어 마스터에게 보고(저장소에는 topics 태그만).
8. **검사**: `py scripts/validate_field_index.py` 와 `py scripts/scan_sealed.py --staged`.

## 전환 처리
- **F2 → F1**: 해제 시각이 지나면 `f1_converted_at` 기록 후 `source-ingest`로 공개 원천 등록.
- **F3 → F1**: 마스터 기사 보도 후 `f1_converted_at` 기록. 이때부터 invest·public 모드 사용 가능.
- **공개 확인**: 공시·회사 발표·타 매체로 확인되면 `publicly_confirmed_at`, `confirm_source_id`, `lead_days`(입력일→확인일), `outcome: confirmed`.

## 출력 (마스터에게만, 화면으로)
```
[필드 인텔] FI-0007 | F3 | B2 | co-skhynix | hbm4;qualification
대조: 기존 테제 th-… 와 일치 / C-… 와 상충
공개 확인 신호: ① … ② …
```

## 흔한 실수
- 등급을 낙관적으로 판정(F3를 F1로) → 기본값은 보수적.
- topics에 사실상 원문을 씀 → 태그 수준으로.
- 엠바고 자료 요약을 브리프에 넣음 → 해제 전엔 "엠바고 1건 대기, 해제 ○○"만.
