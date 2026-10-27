---
name: domain-networking-interconnect
description: 분야 모듈(네트워킹·인터커넥트) — 분해 대상·핵심 변수·최종 검증 지점·흔한 오류·1차 자료처·레이더 키워드. 이 분야 분석·판정 때 참고한다. 초안(draft) — 마스터 검토 전.
user-invocable: false
metadata:
  draft: true
---

# 분야 모듈: 네트워킹·인터커넥트 (draft: true — 마스터 검토 전)

> 공통 골격(BUILD_PROMPT §7.5) 위의 분야별 결정 변수. 확신이 없는 기술 내용은 "마스터 확인 필요"로 둔다. 포토·트랙·EUV·메모리 공정은 마스터 수정이 우선이다.

## 분해 대상
- 스위치 ASIC·NIC → SerDes·리타이머 → 광모듈(플러거블·LPO·CPO) / 구리 케이블(AEC) → 랙·클러스터 토폴로지

## 핵심 변수
- 레인당 속도 vs 포트·시스템 대역폭(구분), 세대(800G→1.6T→3.2T), 광/구리 비중, 전력

## 최종 검증 지점
- 광모듈·스위치 업체 실적, 표준(IEEE 802.3·UEC) 진척, 고객 채택 발표

## 흔한 오류
- 레인당 속도와 시스템 대역폭 혼동
- 전기 구간과 광 구간 경계 혼동
- CPO 데모 = 양산 채택

## 주요 1차 자료처
- OFC, Hot Interconnects, OCP, IEEE 802.3, UEC, 업체 실적

## 레이더 키워드
CPO, LPO, 1.6T, 3.2T, SerDes, 리타이머, UEC, AEC (전체 목록은 `config/keywords.yaml`)