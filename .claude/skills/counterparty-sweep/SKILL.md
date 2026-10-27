---
name: counterparty-sweep
description: 역방향 L1(상대방 공시) 후보를 판정한다: SEC EDGAR 전문 검색·DART 타사 공시 후보(radar/reverse/inbox/)와 DART 공시유보 만료를 신호 레코드로 만든다.
argument-hint: "[YYYYMMDD]"
---

# counterparty-sweep — 상대방 공시 판정 (§11.4 L1)
1. `radar/reverse/inbox/<날짜>/src-edgar-fts*`, `src-dart-counterparty*` 후보를 연다.
2. 원문(url)을 열어 T0 언급 문맥을 확인: 고객·공급사·경쟁사·소송 상대·단순 시장 언급 중 무엇인가. 단순 언급(시장 점유율 나열 등)은 S0.
3. 강도: 상대방의 실명 공급·고객 서술 = S4, 계약서(EX-10)·S-1 고객 서술 = S4, 위험 요인의 공급사 집중 서술 = S3, 완곡어 = S3(→ euphemism-resolve), 단순 언급 = S0~S1.
4. 관련 페어(`knowledge/pairs/`)가 있으면 `pair_id`, 없으면 null로 두고 새 페어 후보를 보고.
5. DART 공시유보: `radar/state/dart_reserve_expiry.json`의 유보 기한을 `knowledge/calendar.csv`에 등록(type 기타, "공시유보 만료 — 계약 상대방 공개 예정").
6. 신호 레코드는 `docs/templates/signal.yaml` 형식, id는 `py scripts/chiip_ids.py signal`, 저장 `radar/reverse/signals/YYYY/MM/<id>.yaml`. 강도는 §11.6(S0~S5). 원문은 짧게 보존, 번역문은 증거가 아니다. 대안 설명 필수.
