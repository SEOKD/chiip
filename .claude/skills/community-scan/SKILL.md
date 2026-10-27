---
name: community-scan
description: 역방향 L8: 독립 뉴스레터(Substack)·Reddit·Hacker News 등 공개 커뮤니티 신호를 판정하고 계정 평판 장부를 갱신한다. 커뮤니티는 단서(S1)이며 insider_like 표시를 한다.
argument-hint: "[YYYYMMDD]"
---

# community-scan — 커뮤니티 (§11.4 L8, §11.9)
1. `radar/reverse/collectors/communities.py` 결과(공개 RSS·공개 API만).
2. 강도 S1(루머). 다른 레이어로 확인되기 전 어떤 출력에서도 사실로 표현하지 않는다(P16).
3. 내부자 성격("우리 팀에서", "사내에서") → `insider_like: true` → invest·public 금지, 기사 모드 단서로만.
4. `knowledge/handle_reputation.csv`: 공개 계정의 주장·확인·부정·평균 선행일. **신원 추적·실명 추정 금지.**
5. 루머가 확인·부정되면 선행성 장부와 평판 장부를 함께 갱신.
6. 개인 게시물 장문 저장 금지(링크 + 자기 말 요지).
7. 신호 레코드: `docs/templates/signal.yaml`, id `py scripts/chiip_ids.py signal`, 저장 `radar/reverse/signals/YYYY/MM/`. 강도 S0~S5(§11.6), 대안 설명 필수, 원문 짧게 보존·번역 병기(번역은 증거 아님).
