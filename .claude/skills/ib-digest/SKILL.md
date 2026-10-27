---
name: ib-digest
description: 마스터가 radar/drop/에 넣은 IB·증권사 리포트를 D:\local-only\licensed\로 옮긴 뒤 자기 말로 요약한다: 의견·목표가·추정치 변경·새 데이터·핵심 논리·치입 판단과의 차이. 원문 문장 복제 금지.
argument-hint: "[파일 이름]"
---

# ib-digest — IB 리포트 요약 (§7.2, §3.1-6)

## 절차
1. `radar/drop/<파일>`을 `D:\local-only\licensed\YYYYMM\`로 **이동**(저장소에 남기지 않음).
2. `source-ingest`로 메타만 등록: doc_type IB리포트, access licensed-local, path "local-only:licensed".
3. 요약(자기 말, 원문 문장·표 복제 금지):
   - 발행사·애널리스트 소속(이름은 공개된 범위), 발행일
   - 의견·목표가: 이전 → 이번
   - **추정치 변경**: 항목·기간·이전→이번(숫자는 사실 정보로 기록 가능)
   - 새 데이터(채널체크·출하 추정 등) — claim_type 추정 또는 채널체크
   - 핵심 논리 3줄
   - 치입 테제·주장과의 차이
4. 컨센서스 변경 기록이 필요하면 `knowledge/models/companies/<ticker>/consensus_log.csv`(6단계)에 날짜·발행사·항목·값.

## 저장
요약은 `outputs/report/YYYYMMDD_ib_<발행사>_<entity>.md`(사용자 소유 요약). 주장 승격 시 `public_corroborated: false`(유료 자료) 기본.

## 금지
PDF·원문 장문을 저장소에 복제, 리포트 내용을 public 모드에 사용.
