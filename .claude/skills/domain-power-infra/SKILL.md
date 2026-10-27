---
name: domain-power-infra
description: 분야 모듈(전력 인프라) — 분해 대상·핵심 변수·최종 검증 지점·흔한 오류·1차 자료처·레이더 키워드. 이 분야 분석·판정 때 참고한다. 초안(draft) — 마스터 검토 전.
user-invocable: false
metadata:
  draft: true
---

# 분야 모듈: 전력 인프라 (draft: true — 마스터 검토 전)

> 공통 골격(BUILD_PROMPT §7.5) 위의 분야별 결정 변수. 확신이 없는 기술 내용은 "마스터 확인 필요"로 둔다. 포토·트랙·EUV·메모리 공정은 마스터 수정이 우선이다.

## 분해 대상
- 계통(송변전) → 변압기·차단기 → UPS·배전 → 랙 전원(HVDC 등) → 전력반도체

## 핵심 변수
- 데이터센터 전력 확보(MW·GW, 시설 기준), 변압기 리드타임·수주잔고, 계통 연계 대기열

## 최종 검증 지점
- 전력 기자재 업체 수주 공시·실적, 전력망 연계 승인, 송변전 설비계획

## 흔한 오류
- 계약 발표 = 매출 인식
- MW 단위 기준(시설 vs IT) 혼동

## 주요 1차 자료처
- HD현대일렉트릭·효성중공업·LS ELECTRIC 공시, ERCOT 등 계통 문서, GE Vernova·Eaton 실적

## 레이더 키워드
800V HVDC, SST, 변압기, UPS, 연료전지 (전체 목록은 `config/keywords.yaml`)