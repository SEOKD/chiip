---
name: conference-tracker
description: 학회 프로그램이 공개되면 T0·T2 기업 저자와 핵심 키워드 세션을 선별해 사전 노트를 만들고, 학회 기간에는 발표·보도·기업 블로그를 일 단위로 추적한다. IEDM·ISSCC·VLSI·Hot Chips·ECTC·OFC·OCP 등.
argument-hint: "[학회 id 예: cf-iedm-2026]"
---

# conference-tracker — 학회 추적 (§10.8)

## 준비
- `knowledge/entities/conferences/<cf-id>.md`: 개최 일정, 프로그램 공개 시기, 논문 공개 경로(IEEE Xplore 등), 과거 핵심 발표. 없으면 만든다.

## 프로그램 공개 시
1. 공식 프로그램 페이지에서 세션·논문 목록 확보(공개 범위).
2. 선별: 저자 소속이 T0·T2 기업(`config/watchlist.csv`·lexicon) 이거나 `config/keywords.yaml` 키워드와 맞는 세션.
3. 추적표 `knowledge/entities/conferences/<cf-id>_tracker.md`:
   | 세션·논문 | 소속 | 주제 | 왜 중요한가(테제 연결) | 확인할 것 | 상태 |
4. 사전 노트: 기업별로 "이 발표에서 확인할 숫자·주장" 3개.

## 학회 기간
- 매일: 발표 요지 보도·기업 블로그·발표 자료 공개 여부 확인 → `paper-digest`로 정리.
- 마스터가 현장 취재한 내용은 `field-intake`로(등급 판정).

## 학회 후
- 핵심 논문별 `paper-digest` 완료, 주장 승격, 테제 영향 정리.
