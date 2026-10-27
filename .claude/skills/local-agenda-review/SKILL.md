---
name: local-agenda-review
description: 미국 주·카운티·시 안건·회의록·인허가 문서(거점 관할)에서 삼성 테일러·오스틴, SK하이닉스 웨스트라피엣 관련 항목을 판정한다. 지방 안건은 공식 발표보다 이르다.
argument-hint: "[site_id]"
---

# local-agenda-review — 지방 안건 (§13.3~13.4)
1. `config/us_gov/sites.yaml`의 관할·`meeting_platforms` → `radar/usgov/adapters/` 수집 결과.
2. 항목 판정: 세금 감면·인프라 협약·용도 변경·건축 허가·전력·용수 계약·경제개발공사 안건.
3. 정책 단계(§13.6 지방 인센티브: 안건 상정 → 의결 → 협약 체결 → 이행 점검)로 기록. **안건 상정 = 투자 확정 금지.**
4. 코드명("Project ○○")이면 `codename-match`.
5. 신호 레코드 layer L2(관할 표시), 일반 시민·직원 개인 정보 저장 금지.
