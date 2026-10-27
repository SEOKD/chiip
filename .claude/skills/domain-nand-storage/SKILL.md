---
name: domain-nand-storage
description: 분야 모듈(NAND·스토리지) — 분해 대상·핵심 변수·최종 검증 지점·흔한 오류·1차 자료처·레이더 키워드. 이 분야 분석·판정 때 참고한다. 초안(draft) — 마스터 검토 전.
user-invocable: false
metadata:
  draft: true
---

# 분야 모듈: NAND·스토리지 (draft: true — 마스터 검토 전)

> 공통 골격(BUILD_PROMPT §7.5) 위의 분야별 결정 변수. 확신이 없는 기술 내용은 "마스터 확인 필요"로 둔다. 포토·트랙·EUV·메모리 공정은 마스터 수정이 우선이다.

## 분해 대상
- 셀(TLC/QLC) → 적층 단수 → 다이 → SSD(컨트롤러·펌웨어·DRAM 캐시) → 기업용·클라이언트

## 핵심 변수
- 비트그로스, ASP, 적층 전환 비용, eSSD 비중, QLC 침투율
- 웨이퍼 감산·가동률

## 최종 검증 지점
- 회사 콜의 eSSD 매출·출하 언급, 고객 인증
- 적층 세대 전환의 생산 비중(공개 수치)

## 흔한 오류
- 적층 단수 = 원가 경쟁력 단정(웨이퍼당 비트·공정 단계 수 비교 필요)
- 기업용 SSD 수요와 NAND 웨이퍼 수요의 시차 무시

## 주요 1차 자료처
- 실적 발표, FMS(Future of Memory and Storage), IMW, ISSCC

## 레이더 키워드
QLC, eSSD, 300단, HBF, PCIe 6.0 SSD (전체 목록은 `config/keywords.yaml`)