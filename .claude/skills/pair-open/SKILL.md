---
name: pair-open
description: 새 관계 가설(A 기업 × B 기업 × 제품)을 페어북(knowledge/pairs/)에 등록하고 사전 신호 플레이북(§11.10)으로 증거 지도를 작성한다. GitHub pair-idea 이슈나 마스터의 가설·필드 인텔에서 시작한다.
argument-hint: "[A] [B] [제품]"
---

# pair-open — 페어 등록 (§11.3, §11.10)
1. 양식 `docs/templates/pair.md`, id `pair-<a>-<b>-<제품>`. `relation_status`는 근거 전까지 `후보`/`미확인`.
2. 관계 가설 1문장, 사실이면 바뀌는 실적 동인·테제.
3. **증거 지도**: 사건 유형(신규 팹·고객 인증·파운드리 고객·합작·공동 개발·이탈)별 선행 흔적을 레이어(L1~L9)·쿼리·감시 대상으로 구체화(`config/query_templates.yaml` 활용).
4. 반대 가설(같은 흔적의 다른 설명) 2개 이상.
5. 필드 인텔로 먼저 안 사안이면 FI 포인터만 연결(원문 금지).
