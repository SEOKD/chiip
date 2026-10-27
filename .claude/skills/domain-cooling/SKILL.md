---
name: domain-cooling
description: 분야 모듈(냉각) — 분해 대상·핵심 변수·최종 검증 지점·흔한 오류·1차 자료처·레이더 키워드. 이 분야 분석·판정 때 참고한다. 초안(draft) — 마스터 검토 전.
user-invocable: false
metadata:
  draft: true
---

# 분야 모듈: 냉각 (draft: true — 마스터 검토 전)

> 공통 골격(BUILD_PROMPT §7.5) 위의 분야별 결정 변수. 확신이 없는 기술 내용은 "마스터 확인 필요"로 둔다. 포토·트랙·EUV·메모리 공정은 마스터 수정이 우선이다.

## 분해 대상
- 칩 발열 → 콜드플레이트(직접 액냉)·침지 → CDU → 시설 냉각

## 핵심 변수
- 랙 전력 밀도(kW/rack), 액냉 침투율, CDU 용량, 시설 전력과 IT 부하 구분

## 최종 검증 지점
- 냉각 업체 수주·실적, 데이터센터 사양 공개

## 흔한 오류
- 시설 전력과 IT 부하 혼동
- 시범 도입 = 표준 채택

## 주요 1차 자료처
- Vertiv·Schneider 실적, OCP

## 레이더 키워드
액냉, direct-to-chip, 침지 냉각, CDU (전체 목록은 `config/keywords.yaml`)