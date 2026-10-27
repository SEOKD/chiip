---
name: morning-brief
description: 07:00 KST 아침 브리프를 만든다. 밤사이 미국·대만·일본 이벤트, 국내 T0 영향, 오늘 일정·지표 발표, 수집 장애를 정리해 outputs/brief/에 저장하고 claude.ai 비공개 Artifact로 공유한다.
argument-hint: "[YYYY-MM-DD]"
---

# morning-brief — 아침 브리프

## 입력 (자동 수집)
- `radar/cards/` 중 전날 16:00 이후 카드
- `radar/state/brief_queue.jsonl` (P2·미판정 항목)
- `radar/state/health.json` (수집 장애)
- `knowledge/calendar.csv` (오늘·내일 일정)
- `knowledge/models/indicators.csv` (오늘 발표 지표)
- 밤사이 미국 장 마감·실적: 웹 검색으로 T2 실적·주요 발표 확인(공개 자료만)

## 형식 (brief 모드, 모바일 가독성)
```
[모드: brief / 범위: 밤사이~07:00 / 기준시각: YYYY-MM-DD 07:00 KST]
■ 한 줄 요약
■ 밤사이 해외 (T2 실적·발표 → T0 연결)
■ 국내 T0 (카드 요약: 등급·한 줄·카드 id)
■ 오늘 일정 / 지표 발표
■ 확인 대기 (1차 출처 미확인, 열린 질문)
■ 수집 장애
```
- 반복 보도 나열 금지. 같은 사건은 1줄.
- 모든 판단 문장에 "(1차 판정)" 또는 근거 카드·주장 id.

## 저장·공유
1. `outputs/brief/YYYYMMDD_morning.md` 저장.
2. **claude.ai 비공개 Artifact로 게시**(§21.9): HTML 페이지로 변환해 게시하고 링크를 마스터에게. **local-only 정보·필드 인텔 대조 결과·엠바고 내용은 넣지 않는다.**
3. 브리프에 포함한 brief_queue 항목은 대기열에서 제거(처리 완료 표시).

## 흔한 실수
- 해외 실적 수치를 출처 없이 기재.
- 엠바고 자료 언급(허용: "엠바고 1건 대기, 해제 ○○"만, 그것도 로컬 저장본에만).
