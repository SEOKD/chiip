# CES 2027 출장 중 운용 모드 (BUILD_PROMPT §18 5단계)

## 출발 전 (12월 마지막 주) 리허설
1. PC 24시간 가동 확인: 절전 끄기, Windows 업데이트 자동 재시작 시간 조정, 작업 스케줄러 `chiip-radar`·`chiip-hourly` 상태 Ready.
2. 원격 확인 수단: 휴대폰에서 텔레그램 알림 수신, GitHub 앱으로 PR·커밋 확인, claude.ai에서 브리프 Artifact 확인.
3. 클라우드 폴백 루틴(선택): `docs/routines/cloud-fallback.prompt.md` — PC가 꺼져도 6시간마다 다이제스트 PR.
4. `py scripts/score_radar.py`로 수집 장애 0건 확인.

## 출장 중
- **시차**: 라스베이거스(PST) = KST − 17시간. 국내 T0 공시는 현지 저녁~새벽에 나온다 → P0 텔레그램 알림만 즉시 확인.
- **현장 취재 입력**: 휴대폰 메모 → 귀국 전이라도 PC 원격 또는 귀국 후 `field-intake`로 등급 판정. F4는 원문 입력 금지(포인터만).
- **브리프**: 아침 브리프는 KST 07:00 = 현지 전날 14:00. 현지 일정에 맞춰 읽는다.
- **CES 추적표**: `knowledge/entities/conferences/cf-ces-2027.md`.

## 귀국 후
- 출장 중 쌓인 brief_queue·카드 검토, 필드 인텔 등급 확정, CES 관련 주장 승격, 테제 갱신.