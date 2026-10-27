---
name: initiation
description: IB식 커버리지 개시 보고서: 사업 구조·실적 동인·경쟁·테제·밸류에이션·리스크·카탈리스트. 새 기업을 본격 커버하기 시작할 때 쓴다(invest 모드, 6단계).
argument-hint: "[기업 id]"
---

# initiation — 커버리지 개시 (§7.4)
**invest 모드 경계**: `D:\local-only`와 F2~F4 필드 인텔 사용 금지, `public_corroborated: true` 주장과 F1만. 출력 하단에 `공개 자료 기반 분석이며 투자 권유가 아님`. 매수·매도 권유·개인 맞춤 투자 조언 금지(훅 public-guard가 강제).

## 구성
1. 한 장 요약: 테제 2문장, 핵심 동인 3개, 반증 조건, 다음 카탈리스트
2. 사업 구조: 사업부·제품 × 역할 × 고객 × 기간(엔티티 파일 매트릭스, 근거 id)
3. 실적 동인: 물량·가격·믹스·가동률·원가 — `model-build` 결과
4. 경쟁·공급망: `supply_relations.csv`, 대안 기술·공급사
5. 테제·인과 사슬: `knowledge/theses/` (미확인 고리 표시)
6. 밸류에이션: `valuation-bridge` 시나리오(강세·기본·약세)·민감도 — 목표주가는 내지 않는다(report 모드 금지 규칙과 동일)
7. 컨센서스 대비: `consensus-gap`
8. 리스크·반증 조건, 카탈리스트 일정(calendar.csv)
9. red-team 판정 첨부
저장 `outputs/invest/YYYYMMDD_initiation_<entity>.md`.
