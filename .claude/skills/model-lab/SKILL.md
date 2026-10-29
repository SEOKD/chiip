---
name: model-lab
description: 모델 고도화 연구실(§21.14). 매일 영어권 학계·금융업계 새 논문·실무 자료(radar/literature.py 수집분)를 읽고 치입 밸류에이션·포커스·텐배거 모델에 쓸 파라미터·구조 변경을 제안서로 쓴다. 주 1회 피팅 하네스로 표본 외 검증 후 채택 여부를 판정하고 연구 노트를 낸다. 예약 작업 chiip-model-lab 또는 마스터 요청 시.
argument-hint: "[daily | weekly | 논문 URL]"
---

# model-lab — 학습·파라미터·피팅 (ADR-010 §3·§4)
고도화 = 파라미터를 만들고 피팅하는 과정. 장부는 `knowledge/models/params/registry.yaml` (`py scripts/fit/registry.py --list`, `--check`).

## daily (매일)
1. `py radar/literature.py --top 15` — 수집 + 관련도 상위 목록.
2. 상위에서 **최대 3편**을 고른다. 기준은 "치입 모델에 실제로 쓸 수 있는가"(관련도 점수는 참고). 초록·공개 본문만 읽는다(유료벽 우회 금지).
3. 노트 `knowledge/models/lab/notes/YYYYMMDD.md` — 편마다:
   - 주장 1문장 / 방법 / 데이터(시장·기간·표본) / 효과 크기(숫자·단위) / 표본 외·재현 증거 / 한계
   - **치입 적용**: 어떤 모델·파라미터에, 어떻게(새 파라미터·사전값 갱신·구조 변경·적용 안 함과 이유)
   - 출처: 제목·저자·연도·URL. 학술 결과는 근거 유형 '추정'. 이상 현상 문헌은 재현 실패 가능성을 적는다.
   - 반도체·AI HW 산업 데이터 논문(예: 캐파 투자 추정)은 `article-pitch`·`capa-update` 재료로도 표시.
4. 적용할 것이 있으면 제안서 `knowledge/models/lab/proposals/MLP-YYYYMMDD-NN.md`:
   - 대상 파라미터 id(새것이면 등록부에 `status: proposed`로 추가) / 현재값 → 제안 사전값과 근거 / 검증 계획(데이터·목표 변수·손실·walk-forward 설정) / 채택 기준(등록부 `adoption`) / 예상 영향.
5. '원문 확인 대기' 사전값(예: `config/tenbagger.yaml` factors basis)을 하루 1건씩 원문으로 확인해 basis·source를 갱신. 값을 바꾸면 config·등록부·`changelog.csv`를 함께.
6. 공개 수치 사전값: 다모다란 월간 내재 ERP 등은 날짜·URL과 함께 `prm-val-erp-us` 등에 기록.

## weekly (일요일)
0. **Proviser 작업 지시를 먼저**(마스터 지시 2026-10-29 — 단계적 고도화): `knowledge/models/params/queue.yaml`(`py scripts/fit/stepwise.py --status --write`가 매일 갱신)을 위에서부터 처리한다. 0단계 '데이터 확보'는 등록부 fit.data·target·method를 정의(자료가 정말 없으면 '필요 자료'로 남김), 1단계 '기존 피팅'은 아래 1~3, 2단계 '잔차 진단'의 새 파라미터 제안은 `stepwise.can_adopt_extension(model, 기존 손실, 확장 손실, 등록부, 확장 후 파라미터 수)` — 짝지은 표본 외 검정 + 누적 시도 수 본페로니 보정 + 관측 수 규칙을 모두 통과할 때만 채택. 1단계가 끝나지 않은 모델에 새 파라미터를 넣지 않는다.
1. 데이터가 있는 제안서부터 `scripts/fit/harness.py`로 검증: `evaluate(series, fit_fn, predict_fn, prior, k, min_train)` → `adoption_decision(...)`. 검증 스크립트는 `scripts/fit/jobs/<param>.py`로 남긴다(재실행 가능해야 함).
2. 통과: 등록부 value·status·fit 블록 갱신 + binding 위치 config를 Edit + `registry.py --check` 일치 확인 + `changelog.csv` 한 행. 상대 변화 20% 이상(`registry.needs_approval`)이면 config는 그대로 두고 `status: fitted` + `docs/TODO_MASTER.md`에 승인 요청.
3. 실패: 제안서에 결과·이유를 적고 상태 유지. 실패도 기록이다.
4. 성적표: `py scripts/score_predictions.py`(마스터·치입 브라이어), `harness.calibration`으로 과신 구간 확인.
5. 주간 '모델 연구 노트' — `outputs/report/lab/YYYYMMDD.md` + claude.ai 비공개 Artifact: 이번 주 배운 것(3줄) / 바뀐 파라미터·표본 외 성과 / 기각된 제안 / 다음 주 검증 계획 / 데이터 병목.

## 금지
- 매일 피팅·채택(과적합). 표본 외 검증 없는 채택. 마스터 고정값(`fixed_by_master: true`) 변경.
- 논문 한 편으로 구조 변경(재현·표본 외 근거 필요). 원문 전체 복제.
