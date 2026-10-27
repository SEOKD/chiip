---
name: weekly-review
description: 주간 리뷰(토요일 오전): 테제별 변화, 지표 변화, 예측 진행, 다음 주 카탈리스트, 레이더·역방향·필드 인텔 성능. outputs/brief/에 저장하고 claude.ai 비공개 Artifact로 공유.
argument-hint: "[주차 YYYY-Www]"
---

# weekly-review — 주간 리뷰 (§7.2)
## 입력
- 지난 7일 카드·주장(novelty 신규·수정), 테제 파일 판단 변경 이력
- `py scripts/score_radar.py`, `score_reverse.py`, `score_field_intel.py`, `score_predictions.py` 결과
- `knowledge/models/indicators.csv`, `mirror_monthly.csv` 변화
- 다음 주 `knowledge/calendar.csv`
## 형식
```
[모드: brief / 범위: YYYY-Www / 기준시각: …]
■ 이번 주 한 문장
■ 테제별 변화 (강화·약화·무관, 근거 id)
■ 지표·거울 데이터
■ 예측 원장 (만기 도래·판정)
■ 다음 주 카탈리스트 (event-preview 필요 목록)
■ 시스템 성능 (탐지 지연·누락·장애·경보 정밀도)
■ 개선 제안 (원천·키워드·규칙 — 마스터 승인 대상)
```
## 저장·공유
`outputs/brief/YYYY-Www_weekly.md` + claude.ai 비공개 Artifact(로컬 전용 정보 제외, 필드 인텔은 source_class 집계만).
