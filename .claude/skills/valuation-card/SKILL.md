---
name: valuation-card
description: 종목 밸류에이션 카드(invest 모드). 계산 엔진(scripts/valuation/engine.py)의 수치 — 멀티플 프리미엄·EPS 리비전·수익률 분해·역DCF 내포 성장·반영도 지수·내러티브 강도 — 를 해석하고, 모델 몫인 시나리오(약세·기본·강세)와 내러티브 단계를 근거와 함께 작성한다. 실적 발표 후·큰 뉴스 후·마스터 요청 시.
argument-hint: "[기업 id] (예: co-skhynix)"
---

# valuation-card — 밸류에이션 카드 (docs/valuation/framework.md, ADR-008)
**invest 모드 경계**: `D:\local-only`와 F2~F4 필드 인텔 사용 금지, `public_corroborated: true` 주장과 F1만. 출력 하단 `공개 자료 기반 분석이며 투자 권유가 아님`. **목표주가·매수/매도 의견 금지** — "시나리오 가치 범위·시장 내포 기대"로 쓴다. 개인 맞춤 투자 조언 금지.

## 역할 분담 — 숫자는 코드, 판단은 모델
- 코드(손대지 않는다): `py scripts/valuation/engine.py --card <id>` — 모든 수치. 카드의 숫자는 이 출력에서만 가져오고, 없는 칸은 "미확인".
- 모델(이 스킬): ① 시나리오 작성 ② 내러티브 단계 판정 ③ 해석·반대 검증·반증 조건.

## v2 정량 블록 (2026-10-28, docs/valuation/v2_architecture.md)
- 종목에 `knowledge/models/companies/<id>/drivers.yaml`(시나리오·확률·성장/마진 경로·재투자 효율·투하자본·시가)이 있으면 `py scripts/valuation/v2/run.py <id> --save`로 정량 블록을 만들어 카드에 붙인다: WACC 분해, 시나리오별 가치/시총, 몬테카를로 분포, P(5년 뒤 ≥1.5·2·3·10배), 시장 내포 CAGR과 기저율 백분위, 2배·10배에 필요한 CAGR, 금리 +50bp 민감도, 알파 정량 제안.
- 표기: 시가총액 대비 배수·확률·필요 가정만(주당 가치·목표주가 금지 — 마스터 결정). 동인 가정마다 근거와 '근거 약함' 표시. 기저율 표본 편향 문구를 지우지 않는다.
- 결과가 직관과 크게 다르면 먼저 가정(성장 경로·장기 마진·재투자 효율·WACC)을 점검하고, 시장 내포 가정과의 차이로 설명한다(“시장이 틀렸다”는 consensus-gap 절차 후에만).

## 절차
1. `py scripts/valuation/engine.py --card <id>` 실행. 데이터 상태(스냅숏 날짜·주의 플래그)부터 적는다.
2. **시나리오** (`knowledge/models/valuation/scenarios.csv`에 행 추가 — 수정하지 않고 새 as_of로 추가):
   - 열: `as_of,id,scenario(bear|base|bull),metric(EPS|BPS|PRICE),value,multiple,prob,currency,horizon,evidence_ids,narrative_ids,note`
   - 하위 섹터 기본 방법(`config/valuation.yaml` subsectors)을 따른다. 예: 메모리 = 2년 평균·정상화 EPS × P/E 또는 BPS × P/B(사이클 밴드), AI 가속기 = CY+1·+2 EPS × P/E.
   - 각 시나리오의 숫자를 정당화하는 사건(주장 id·카드 id)과 내러티브 id를 적는다. 근거 없는 숫자는 쓰지 않는다. 세 확률 합은 1.
   - 배수는 피어·자기 역사·공개 보도된 IB 배수 범위(framework.md §2, 출처 명시) 안에서 고르고 이유를 note에.
   - 저장 후 `py scripts/valuation/engine.py` 재계산 → 내포 강세 확률·비대칭 확인.
3. **내러티브 단계**: 종목의 상위 내러티브마다 framework.md §7 단계표로 판정하고 `knowledge/narratives/registry.yaml`의 `stage`·`stage_reason`(근거 숫자·id)·`stage_as_of`를 갱신. 강도(언급 건수)는 관심의 크기이지 사실의 증거가 아니다.
4. **카드 작성** (공통 구조):
```
[모드: invest / 범위: <기업> 밸류에이션 / 기준시각: …]
■ 결론 (2~3문장: 지금 가격이 무엇을 가정하고 있나 — 펀더멘털 몫 vs 내러티브 몫)
■ 인과 사슬 (뉴스·주장 id → 바뀐 층: EPS 리비전 / 멀티플 / 내러티브 → 반영도)
■ 근거 표 (엔진 수치: 멀티플·피어 대비·리비전·수익률 분해·내포 성장·반영도 구성 — 기준일·출처)
■ 시나리오 (약세·기본·강세 가치, 확률, 내포 강세 확률, 비대칭 — "목표주가" 표현 금지)
■ 내러티브 (단계·숫자 전환 여부·반증 조건)
■ 반대 검증 (아래 함정 목록 중 해당 항목)
■ 반증 조건·다음 확인 (calendar.csv 일정)
■ 종료 상태 (판단 가능 / 조건부 판단(가정 명시) / 핵심 근거 부족(필요 자료 명시))
■ 10점 평가 (논리·사업 경쟁력·투자 매력·증거 확신도·기사 가치 분리, 감점 요인·상향 조건)
공개 자료 기반 분석이며 투자 권유가 아님
```
5. 저장: `outputs/invest/valuation/YYYYMMDD_<id>.md`. 결론은 red-team 검토 대상.

## 함정 (반대 검증 체크)
- 사이클 업종(메모리·장비·기판)의 NTM EPS가 고점이면 P/E가 낮아 보이고 내포 성장이 왜곡된다 → 정상화 EPS·P/B 밴드로 교차 확인.
- 잔차 프리미엄 = 내러티브 프리미엄 **후보**. 회귀에 없는 변수(순현금·지배구조·통화)일 수 있다.
- 반영도 높음 ≠ 하락 예정, 낮음 ≠ 저평가 확정. "시장이 간과했다"는 consensus-gap 통과 후에만.
- 리비전 상향 → 주가 상승, 주가 급등 → 펀더멘털 변화(금지표) 연결 금지. 수익률 분해로 몫을 나눠 말한다.
- 추정치 수동 입력·ADR 통화 불일치·애널리스트 수 적음(분산 큼) 플래그는 결론의 확신도를 낮춘다.
- 같은 원출처 재인용이 내러티브 강도를 부풀린다.
