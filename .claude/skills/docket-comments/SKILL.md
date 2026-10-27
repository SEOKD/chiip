---
name: docket-comments
description: Regulations.gov 규칙 의견 수렴 문서함에서 T0·고객·장비사·업계 협회가 낸 의견서를 찾아 입장·사업 데이터·요청을 요약한다. REGULATIONS_GOV_API_KEY 필요.
argument-hint: "[docket id]"
---

# docket-comments — 의견서 분석 (§13.5⑥)
1. 문서함(docket)의 의견서 목록에서 제출자명으로 T0·고객·협회(lexicon·watchlist) 필터.
2. 의견서별: 입장(찬성·반대·수정 요청), 제시한 사업 데이터(매출·고용·투자 — 숫자는 위치 인용), 요청 사항.
3. 기업이 정부에 직접 쓴 문서 → 주장 승격 시 speaker_type 기업, claim_type 확정사실(그 기업의 진술로서).
4. 요약 저장 `outputs/report/YYYYMMDD_docket_<id>.md`.
