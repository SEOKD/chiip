---
name: paper-trail
description: 역방향 L2(정부·지자체·인허가)·L4(특허·상표·학술) 서류를 추적해 신호 레코드로 만든다. EIASS·NTIS·지자체 고시, 미국 인허가, 공동 특허·상표 출원·공동 논문(OpenAlex).
argument-hint: "[페어 id 또는 기업 id]"
---

# paper-trail — 서류 추적 (§11.4 L2·L4)
1. 대상 페어의 증거 지도에서 L2·L4 항목을 고른다.
2. 원천별 확인(공개 자료만, 접근 가능성은 §21.6):
   - 국내: EIASS 평가서 초안(생산 계획·용수·전력·일정), 지자체 고시(산업단지 변경·건축 허가), NTIS 과제 참여 기업(공동 개발 관계)
   - 미국: 주 환경 허가 신청서(설비 목록·가동 규모), 주 인센티브 안건 — 미국 원천은 §13 엔진과 공유
   - 특허·상표: 공동 출원인·권리 양도, 발표 전 상표 출원(제품명·코드명)
   - 학술: `radar/reverse/collectors/openalex.py` 결과(국내 기업 저자 × 외부 기업 저자 공동 논문)
3. 강도: 공적 서류·공동 특허·상표 = S3, 공동 논문 = S2, 정부 과제 참여 = S3.
4. 신호 레코드: `docs/templates/signal.yaml`, id `py scripts/chiip_ids.py signal`, 저장 `radar/reverse/signals/YYYY/MM/`. 강도 S0~S5(§11.6), 대안 설명 필수, 원문 짧게 보존·번역 병기(번역은 증거 아님).
