---
name: evening-wrap
description: 장 마감 후(16:30 KST 이후) 브리프. 당일 T0 뉴스·카드, 미국·일본·EU·영국·한국 상장 반도체·AI 하드웨어·소프트웨어 종목의 공식 보도자료(5분류), 주가 반응(공개 자료로 확인 가능할 때만), 내일 일정을 outputs/brief/에 저장하고 claude.ai 비공개 Artifact로 공유한다.
argument-hint: "[YYYY-MM-DD]"
---

# evening-wrap — 저녁 브리프

## 입력
- 당일 `radar/cards/` 전체, `radar/state/brief_queue.jsonl`
- **글로벌 공식 발표**: `py radar/pollers/press_wire.py --digest YYYYMMDD` 출력(PR Newswire·Business Wire 보도자료를 분류×지역으로 묶은 표). 전날 16:40 이후분이 빠지지 않게 전날 날짜 digest도 함께 본다.
- SEC 6-K 등 1차 공시: inbox의 `src-sec-self` 항목
- DART·네이버는 수집 제외(2026-10-28 마스터 결정). 국내 공시는 웹에서 공개 확인된 것만 짧게
- 주가: 공개 웹에서 확인 가능할 때만 종목·지수 대비 등락. 못 하면 "미확인"
- `knowledge/calendar.csv` 내일 일정
- **밸류에이션 레이더**: `py scripts/valuation/engine.py --digest evening` 출력(한국 장 마감 반영 — T0 표를 먼저)

## 글로벌 공식 발표 절 작성 규칙
- 분류는 마스터 지정 5개 표현 그대로: **Commercial contract wins/terminations · Corporate Financials · Market pressures · Mergers and Acquisitions · Innovation and expansions**. 지역은 미국·일본·EU·영국·한국.
- digest의 분류는 제목 규칙 기반 1차 분류다. 읽어 보고 틀린 분류는 옮기고, 반도체·AI 하드웨어·소프트웨어와 무관한 항목(예: 일반 IT 서비스·산업 자동화 단순 소개)은 뺀다. 뺀 개수는 끝에 한 줄로.
- 항목마다: `[지역] 회사(거래소: 티커) — 무엇(한 문장, 자기 말) — 왜 중요한가(T0·공급망·테제 연결, 없으면 생략) — 링크`. 보도자료 문장을 옮겨 쓰지 않는다.
- 보도자료는 회사 주장이다. 수치는 "회사 발표 기준"으로 적고, 잘못된 연결 금지표(협력·MOU → 매출, 투자 발표 → 공급 증가 등)를 지킨다.
- T0·공급망(`knowledge/models/supply_relations.csv`)과 연결되는 항목을 위로. 연결 근거가 없으면 "연결 미확인".
- 0건인 분류는 "해당 없음"으로 한 줄.

## 형식
```
[모드: brief / 범위: YYYY-MM-DD 장중 / 기준시각: … KST]
■ 오늘의 T0 (기업별: 뉴스·카드 id·주가 반응)
■ 글로벌 공식 발표 (5분류 × 지역)
  - Commercial contract wins/terminations
  - Corporate Financials
  - Market pressures
  - Mergers and Acquisitions
  - Innovation and expansions
■ 밸류에이션 레이더 (오늘 T0 뉴스·공식 발표가 리비전·멀티플·내러티브 중 어디를 움직였나)
■ 판정 변경 (아침 대비 바뀐 카드: 1차판정→검증완료, 등급 조정)
■ 주장 승격 후보 (claim-intake 대기 목록)
■ 내일 일정
■ 수집 장애
```
- "주가 급등 → 펀더멘털 변화" 연결 금지. 원인 사건을 특정 못 하면 "원인 미확인".
- 밸류에이션 레이더 절: digest 숫자는 그대로, 해석 2~4줄(오늘 사건 → 바뀐 층, "(1차 판정)"), 수익률 분해로 주가 변화의 EPS 몫·P/E 몫을 나눠 말한다. 반영도는 방향 예측이 아님. 매수·매도·목표주가 금지, 절 끝 `공개 자료 기반 분석이며 투자 권유가 아님`. 큰 변화 종목은 `valuation-card` 후보로.

## 저장·공유
`outputs/brief/YYYYMMDD_evening.md` + claude.ai 비공개 Artifact(로컬 전용 정보 제외).
