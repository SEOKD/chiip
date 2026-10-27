---
name: flash-note
description: IB식 First Take. 이벤트 후 30분 안에 1쪽 메모: 무엇이 나왔나 / 기대 대비 / 실적 동인 영향 / 열린 질문 / 다음 확인. 반드시 '1차 판정, 미검증' 표시. P0 카드가 나오면 impact-card 다음에 쓴다.
argument-hint: "[카드 id]"
---

# flash-note — 플래시 노트 (BUILD_PROMPT §7.2, P13)

## 입력
완성된 영향 카드(`radar/cards/**/<id>.yaml`)와 1차 출처.

## 형식 (1쪽, flash 모드)
```
[모드: flash / 범위: <사건 1건> / 기준시각: … KST] — 1차 판정, 미검증
■ 무엇이 나왔나 (2문장, 1차 출처 기준. 보도뿐이면 "보도 기준" 명시)
■ 기대 대비 (event-preview 사전 노트·컨센서스가 있으면 비교, 없으면 "기대치 미확인")
■ 실적 동인 영향 (기업·동인·방향·규모 기준·시점)
■ 2차 영향 (공급 관계 경로, 신뢰도)
■ 열린 질문 (3개 이내)
■ 다음 확인 (사건·날짜)
■ 야마 후보
```
저장: `outputs/flash/YYYYMMDD_HHMM_<entity>_<event>.md`. 30분 목표. 이후 확인되면 카드 `verification: 검증완료`로 바꾸고 노트 하단에 정정·보강 기록(원문 덮어쓰지 않음).

## 금지
과장된 확신, "시장이 간과" 단정, 엠바고·local-only 내용.
