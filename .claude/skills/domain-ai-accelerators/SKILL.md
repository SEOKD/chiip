---
name: domain-ai-accelerators
description: 분야 모듈(AI 가속기(GPU·ASIC·인터커넥트 IP)) — 분해 대상·핵심 변수·최종 검증 지점·흔한 오류·1차 자료처·레이더 키워드. 이 분야 분석·판정 때 참고한다. 초안(draft) — 마스터 검토 전.
user-invocable: false
metadata:
  draft: true
---

# 분야 모듈: AI 가속기(GPU·ASIC·인터커넥트 IP) (draft: true — 마스터 검토 전)

> 공통 골격(BUILD_PROMPT §7.5) 위의 분야별 결정 변수. 확신이 없는 기술 내용은 "마스터 확인 필요"로 둔다. 포토·트랙·EUV·메모리 공정은 마스터 수정이 우선이다.

## 분해 대상
- 워크로드(학습·추론) → 시스템(랙) → 가속기(다이·HBM·패키지) → 인터커넥트(NVLink류·UALink·이더넷) → 소프트웨어

## 핵심 변수
- 출하량(단위 명시: GPU·패키지·랙), 세대 전환 일정, HBM 탑재량, 고객(하이퍼스케일러) CAPEX
- 커스텀 ASIC 비중

## 최종 검증 지점
- 가속기 업체 실적·가이던스, 하이퍼스케일러 CAPEX, 공급망 월매출

## 흔한 오류
- 랙 단위와 GPU 단위 혼동
- 로드맵 발표 = 출하 일정 확정
- '고객 투자 확대 → 메모리 공급사 매출' 직결

## 주요 1차 자료처
- NVIDIA·AMD·Broadcom 실적, Hot Chips, ISSCC, OCP

## 레이더 키워드
GPU, 커스텀 ASIC, TPU, NVLink, UALink (전체 목록은 `config/keywords.yaml`)