---
name: triangulate
description: 페어별 역방향 신호를 누적해 독립성·점수·경보를 판정하고(scripts/triangulate.py) 확인 취재 질문을 만든다. 결론은 '정황'으로 쓰고 red-team 검토를 받는다.
argument-hint: "[pair_id]"
---

# triangulate — 삼각측량 (§11.6)
1. `py scripts/triangulate.py <pair_id>` → 독립 신호 수·점수·최강 강도·경보.
2. 독립성 재확인: 같은 원출처 재인용이 독립으로 들어가 있지 않은가.
3. 경보면 영향 카드(`radar/cards/`)에 `reverse` 블록(§11.12: pair_id, signals, layers, strongest, convergence, official_status, confirm_questions) 작성.
4. **확인 취재 질문 3개**(로컬 세션) — 누구에게 무엇을(취재원 이름 없이 직무 범주로).
5. 페어 파일 '신호 기록'·'현재 상태' 갱신.
6. 결론 문장 + claim id를 red-team 에이전트에 넘긴다. **수렴은 사실이 아니다**(P19).
