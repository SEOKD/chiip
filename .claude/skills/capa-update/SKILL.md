---
name: capa-update
description: 새 근거로 팹 캐파 모델(fab_capacity.csv)을 갱신하고 웨이퍼↔비트/다이 환산을 점검한다. 증설·장비 반입·가동 소식이 나올 때 쓴다.
argument-hint: "[fab id 또는 근거]"
---

# capa-update — 캐파 모델 갱신 (§5.5)

## 원칙
- 단위: 300mm 환산 월 1,000장(kwpm). `capacity_basis`: 공시|공개보도|업계추정|자체추정. **봉인 출처 기반 수치는 저장소에 쓰지 않는다**(`D:\local-only\sealed\capa_overlay.csv` 전용).
- `status`: 계획|착공|골조완료|클린룸완료|장비반입|램프|풀가동|전환중. 명목 캐파와 실투입을 섞지 않는다.

## 절차
1. 근거를 `source-ingest`로 등록하고 evidence_ids에 연결.
2. 해당 행(fab_id·building·phase) 갱신 또는 추가. 날짜 필드(cleanroom_ready·tool_in_start·mp_start·full_ramp)는 근거가 있는 것만.
3. **환산 점검**: 웨이퍼 → 다이(다이 크기·수율 가정 명시) → 비트. 가정은 자체추정으로 표시.
4. 금지표: "투자 발표 → 공급 증가", "명목 캐파 → 판매 가능 생산량".
5. `py scripts/check_units.py knowledge/models/fab_capacity.csv`.
