---
name: source-ingest
description: 원문(공시·어닝콜·IR자료·보도자료·논문·기사·IB리포트 등)을 치입 원천으로 등록한다. 새 자료를 분석하기 전, 주장을 만들기 전에 반드시 먼저 쓴다. 메타데이터 작성, 재인용 판정, 라이선스 자료의 local-only 분리를 처리한다.
argument-hint: "[URL 또는 파일 경로]"
---

# source-ingest — 원천 등록

## 목적
모든 주장(claim)은 등록된 원천 id(`S-YYYYMMDD-NNN`)를 근거로 가진다. 이 스킬은 원천을 한 번만, 올바른 위치에, 올바른 메타데이터로 등록한다.

## 입력
URL, 로컬 파일, 또는 마스터가 붙여 넣은 텍스트.

## 절차
1. **접근 등급 판정**
   - `public`: 공시·회사 보도자료·공개 논문·정부 문서 등 재배포 가능 → `sources/raw/YYYY/MM/`에 저장 가능.
   - `paywalled`: 유료 기사·유료 DB → 원문 저장 금지. 메타 + 자기 말 요지 + 링크만.
   - `licensed-local`: IB·증권사 리포트, 유료 구독 자료 → 원문은 `D:\local-only\licensed\`로 이동. 저장소에는 메타만, `path: "local-only:licensed"`.
   - 엠바고 자료(해제 시각 지정)는 이 스킬이 아니라 `field-intake`(F2)로 보낸다.
2. **중복·재인용 판정**: `sources/index.yaml`에서 같은 URL·제목·발행처·발행일을 찾는다.
   - 같은 문서면 등록하지 않고 기존 id를 쓴다.
   - 다른 매체가 같은 원출처를 재인용한 기사면 새 id를 주되 `origin_id`에 원출처 id를 넣는다(P6). 원출처가 아직 없으면 원출처(공시·회사 발표)를 먼저 찾아 등록한다.
3. **id 발급**: `py scripts/chiip_ids.py source <발행일 YYYYMMDD>`.
4. **메타 작성** (`sources/index.yaml`에 추가, BUILD_PROMPT §5.4 형식):
   `id, title, publisher, doc_type, published(원 시간대 그대로 + KST 병기 가능), retrieved(KST), language, path, url, origin_id, access`.
   - `doc_type`: 공시|어닝콜|IR자료|보도자료|기술블로그|논문|학회발표|표준문서|특허|통계|기사|IB리포트|사용자보도|기타
5. **원문 저장**(public만): `sources/raw/YYYY/MM/<id>.<ext>`. HTML은 본문 텍스트만 `.md`로. PDF는 그대로.
6. **검사**: `py scripts/scan_sealed.py sources/index.yaml`.

## 출력
등록된 id 목록과 각 항목의 접근 등급·재인용 여부 한 줄 요약.

## 완료 기준
- 필수 메타 11개 완비, 중복 없음, 재인용이면 `origin_id`가 원출처를 가리킴.
- licensed·paywalled 원문이 저장소에 없음.

## 흔한 실수
- 언론 기사를 1차 출처로 등록(원출처 공시를 찾지 않음).
- 발행 시각을 KST로 바꾸며 원 시간대 정보 손실.
- IB 리포트 PDF를 `sources/raw/`에 저장.
- 같은 어닝콜의 스크립트와 슬라이드를 하나로 묶음 → 문서가 다르면 id를 따로.
