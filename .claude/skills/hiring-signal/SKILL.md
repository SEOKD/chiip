---
name: hiring-signal
description: 역방향 L6: 타사(팹리스·고객·장비사) 공개 채용 공고에 나오는 국내 기업 언급(예: '삼성 파운드리 PDK 경험', 'HBM 통합 경험')을 판정한다. 공개 잡보드 API(Greenhouse·Lever 등)만.
argument-hint: "[기업 또는 키워드]"
---

# hiring-signal — 타사 채용 속 흔적 (§11.4 L6)
1. `radar/talent/collectors/jobs_boards.py`가 모은 타사 공고 중 lexicon 이름이 나온 것.
2. 문맥 판정: 고객·파트너 관계 노출(예: 특정 파운드리 공정 설계 경험 요구 = 해당 파운드리 고객 정황, S2), 단순 경력 우대 = S1.
3. 삼성·SK하이닉스 **자체** 채용 추적은 §12 인재·조직 레이더 담당 — 여기서는 타사 공고만.
4. LinkedIn·Glassdoor·블라인드 수집 금지. 채용 담당자 개인 정보 저장 금지.
5. 신호 레코드: `docs/templates/signal.yaml`, id `py scripts/chiip_ids.py signal`, 저장 `radar/reverse/signals/YYYY/MM/`. 강도 S0~S5(§11.6), 대안 설명 필수, 원문 짧게 보존·번역 병기(번역은 증거 아님).
