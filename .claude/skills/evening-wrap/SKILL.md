---
name: evening-wrap
description: 장 마감 후(16:30 KST 이후) 브리프. 당일 T0 공시·뉴스, 주가 반응(공개 자료로 확인 가능할 때만), 카드 요약, 내일 일정을 outputs/brief/에 저장하고 claude.ai 비공개 Artifact로 공유한다.
argument-hint: "[YYYY-MM-DD]"
---

# evening-wrap — 저녁 브리프

## 입력
- 당일 `radar/cards/` 전체, `radar/state/brief_queue.jsonl`
- DART 당일 공시(카드·inbox의 src-dart 항목)
- 주가: 공개 웹에서 확인 가능할 때만 종목·KOSPI 대비 등락. 못 하면 "미확인"
- `knowledge/calendar.csv` 내일 일정

## 형식
```
[모드: brief / 범위: YYYY-MM-DD 장중 / 기준시각: … KST]
■ 오늘의 T0 (기업별: 공시·뉴스·카드 id·주가 반응)
■ 판정 변경 (아침 대비 바뀐 카드: 1차판정→검증완료, 등급 조정)
■ 주장 승격 후보 (claim-intake 대기 목록)
■ 내일 일정
■ 수집 장애
```
- "주가 급등 → 펀더멘털 변화" 연결 금지. 원인 사건을 특정 못 하면 "원인 미확인".

## 저장·공유
`outputs/brief/YYYYMMDD_evening.md` + claude.ai 비공개 Artifact(로컬 전용 정보 제외).
