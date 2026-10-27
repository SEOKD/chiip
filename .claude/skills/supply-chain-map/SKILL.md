---
name: supply-chain-map
description: 시스템(가속기·서버·스위치 등)을 BOM으로 분해해 부품별 공급사·역할·관계 상태·가치 귀속을 정리하고 supply_relations.csv에 반영한다. 2차 영향 전파의 그래프를 만드는 작업.
argument-hint: "[시스템 이름]"
---

# supply-chain-map — 공급망 지도 (§5.6, §7.3)

## 절차
1. `knowledge/models/bom/<system>.csv`: `component,layer,qty_per_system,unit,supplier_candidates,value_share_est,basis,evidence_ids`.
2. 부품별 공급사와 **관계 상태**(확정공급|과거공급|인증·평가|후보|분석상추정|미확인)를 근거와 함께.
3. `knowledge/models/supply_relations.csv`에 행 추가: `supplier,customer,product,layer,role,relation_status,share_est,period,evidence_ids,confidence,updated`.
4. 가치 귀속: 시스템 가격 중 부품·기업별 비중 추정(가정 명시, 자체추정).
5. T0 우선: 이수페타시스·두산 전자BG·롯데에너지머티리얼즈 → MLB·CCL·동박 → 가속기·스위치 고객, 삼성전기·LG이노텍 → FC-BGA → 가속기·CPU, SK하이닉스·삼성전자 → HBM → 가속기.

## 금지
보도 한 건으로 '확정공급'. "고객 투자 확대 → 특정 공급사 매출" 연결(금지표).
