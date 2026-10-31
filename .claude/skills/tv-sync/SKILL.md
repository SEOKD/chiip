---
name: tv-sync
description: TradingView 와치리스트와 Chiip 레이더를 양방향으로 맞춘다. 와치리스트 종목을 알파·텐배거 발굴 레이더에 넣고, Chiip이 찾은 종목이 와치리스트에 없으면 폴더(국가)·섹션(섹터)에 맞게 추가한다. 예약 작업 chiip-tv-sync 또는 마스터 요청 시.
---

운영 규칙: `docs/channels/discovery.md`를 먼저 읽는다.

절차는 `docs/tasks/chiip-tv-sync.md`를 읽고 그대로 따른다.

- 입력: 없음(설정 `config/tradingview.yaml`).
- 지우지 않는다. 마스터가 지운 종목은 다시 넣지 않는다.
- 완료 기준: 호출 수가 rate_budget 이하, 추가한 종목이 응답 목록의 맞는 섹션에 있음, 확인 필요 항목을 보고에 첨부.
