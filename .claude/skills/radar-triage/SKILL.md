---
name: radar-triage
description: 레이더 신규 항목 묶음(JSON 파일)을 빠르게 분류한다. 관련성(티어)·이벤트 유형·1차 출처 여부·novelty·알림 등급(P0~P3)을 1차 판정하고 P0·P1은 영향 카드 초안을 만든다. run_triage.py가 헤드리스로 호출하며, 수동으로 "레이더 판정"을 요청할 때도 쓴다.
argument-hint: "[radar/state/triage_batch.json]"
---

# radar-triage — 레이더 1차 분류

## 입력
`$ARGUMENTS` = 항목 배열 JSON 파일 경로(BUILD_PROMPT §5.12 형식). 파일을 Read로 연다.

## 판정 기준
**알림 등급** (`config/alert_rules.yaml` 참고)
| 등급 | 조건 |
|---|---|
| P0 | T0의 잠정실적·실적·가이던스 변경·대형 공급계약·대규모 증설/CAPEX 변경·생산 차질. 업계 판도를 바꾸는 T2 발표(주요 고객의 공급사 변경 등) |
| P1 | T0 관련 신제품·인증·양산 진척, T0 대상 IB 의견·목표가 변경, T2 실적, 핵심 지표 서프라이즈 |
| P2 | T1 공시, 학회 논문, 표준, 일반 업계 뉴스(아래 'AI 밸류체인·보유 종목'에 해당하지 않는 것) |
| P3 | 반복·재인용 보도, 관련성 낮음, 광고·주가 시황 단순 나열 |

**AI 밸류체인·보유 종목 (2026-10-29 마스터 지시 — Broadcom–Anthropic 630억 달러 금융·앤트로픽 IPO 신청·Meta 유상증자에 엔비디아 참여·MRVL의 Lumentum 인수 협상이 P2로 묻힌 뒤)**
T0(한국 기업) 연결이 없어도 다음은 **P1 이상**이다. "T0 직접 연결 약함"·"기사라 한 단계 하향"을 이유로 P2로 내리지 않는다(1차 출처 대기는 reason에 적는다).
- 하이퍼스케일러·프런티어 AI 랩(OpenAI·Anthropic·xAI 등)과 칩·인프라 공급사 사이의 계약·금융·투자·CAPEX로 100억 달러 이상, 또는 AI 밸류체인 기업의 자금 조달(유상증자·전환·우선주·회사채·사모 신용·SPV·전략적 지분 투자) 10억 달러 이상.
- 프런티어 AI 랩·AI 인프라 비상장사의 상장 서류(S-1·F-1)와 그 핵심 내용(공급사·위험 요인에 T0·감시 기업 언급).
- 감시 기업(watchlist·valuation universe)의 M&A 협상·인수 보도(Bloomberg·The Information·Reuters·WSJ "is said to"·"in talks" 포함) — 1차 출처 대기로 P1.
- Reuters·Bloomberg·WSJ·The Information의 감시 기업 단독(Exclusive).
- 마스터 보유 종목(config/portfolio.yaml holdings)과 그 related(경쟁사·고객)의 계약·수주·금융·가이던스·M&A 사건. 보유 종목 자체의 실적·M&A·증자는 P0 후보.
- 같은 사건의 후속 기사는 새 사실(참여자·조건·규모 변경)이 있을 때만 P1, 없으면 재인용 P3.
판정 뒤 radar/promote.py가 같은 규칙을 결정론으로 한 번 더 적용한다(모델이 놓친 것 보완).

**보정 규칙**
- 1차 출처(공시·회사 보도자료)가 아닌 보도는 같은 내용이라도 한 단계 낮춰 판단하되, P0 후보면 P1로 두고 `reason`에 "1차 출처 대기".
- 같은 사건을 다룬 여러 기사는 가장 빠른 1건만 P0/P1, 나머지 P3(`reason: 재인용`).
- 제목만으로 판단이 어려우면 낮은 등급 + `reason`에 이유.
- `knowledge/claims/`에 이미 있는 내용이면 novelty 반복 → P3.

**리서치·SNS 항목** (`doc_type: 리서치|SNS`, src-research-feeds·src-research-x — config/research_watch.yaml)
- 리서치 기관·투자자의 의견·추정이다. 이벤트 유형은 원칙적으로 `IB의견변경` 또는 `기타`, what에는 "○○는 …라고 주장"처럼 주체를 붙인다.
- 기본 P2. T0 실적 동인(HBM 점유·가격·고객 인증·CAPEX)에 대한 **새로운 구체 수치·채널체크**면 P1(1차 출처 대기). P0는 주지 않는다 — 경영진 계정(kind 경영진)의 회사 공식 발표 성격 글만 예외적으로 P0 후보.
- 같은 주장을 다른 계정이 퍼 나른 것은 재인용 P3. 글이 인용한 원출처(보도·공시·증권사 자료)가 있으면 open_questions에 적는다.

**정책·행정명령 항목** (`doc_type: 규제·정책` — 미국 연방·주·지방, EU·회원국, 일본·대만·중국. §21.12)
- P0: T0 사업에 직접 닿는 **확정 조치** — 수출통제 최종 규칙·VEU 등 허가 변경, 반도체 관세(232 등) 발동·세율 변경, T0 대상 보조금 최종 계약·취소, 중국의 대한국·대미 수출 금지(희토류·갈륨 등) 발효.
- P1: 반도체·AI 하드웨어·데이터센터·전력에 관한 행정명령, 법 통과·시행, 최종 규칙, 보조금·재정 지원 확정, 세액공제, 국가 AI·반도체 예산(보정예산 포함), 수출통제 규칙안 공개, T0 거점(테일러·오스틴·웨스트라피엣 등) 지방 안건 의결·인허가.
- P2: 발의·의견 수렴·장관 연설·회의 개최·일반 산업 진흥 발표. P3: 무관 분야, 같은 조치의 재게시.
- what에는 단계(발의·규칙안·최종·시행 / 발표·계약·지급)를 반드시 쓴다. 원문 언어(일·중·독·네·프)는 그대로 두고 번역은 병기. 판정 근거가 원문 확인 전이면 "1차 판정, 미검증". 상세 판정은 policy-analyst·fedreg-watch.

**학회·협회 항목** (`doc_type: 학회·협회` — OCP·MLCommons·CXL·UEC·UALink·JEDEC·SEMI·SIA·IEEE 학회 등)
- P1: 표준·사양 발표(JEDEC HBM·LPDDR·GDDR, CXL·UCIe·UEC·UALink 사양), MLPerf 결과, 학회 프로그램·논문 목록 공개(ISSCC·IEDM·VLSI·Hot Chips·ECTC·OFC·OCP Summit — T0·T2 발표가 있으면), 협회 통계(WSTS·SIA 월매출, SEMI 장비 출하·팹 전망, SEAJ), T0·T2가 발표한 세미나 자료.
- P2: 행사 안내·일반 협회 소식. P3: 회원 모집·홍보.
- 세미나·발표 자료는 링크와 요지만(원문 복제 금지). 학회 단위 추적은 conference-tracker.

**이벤트 유형**: 실적|잠정실적|가이던스|수주·공급계약|증설·CAPEX|제품·기술발표|인증·양산|가격|M&A|규제·정책|인사|사고·차질|학회논문|표준|IB의견변경|컨센서스변경|기타

## P0·P1 카드 초안
1. `py scripts/chiip_ids.py card` 로 id 발급.
2. `docs/templates/card.yaml` 형식으로 `radar/cards/YYYY/MM/<id>.yaml` 작성. 채울 것: item_ids, first_seen_source, detected_at, published_at, entities, event_type, headline_ko, what_happened(2문장, 확인된 사실만), primary_source_confirmed, alert_level, verification: 1차판정, open_questions. 영향(first_order 등)은 `impact-card`가 채운다 — 모르면 비워 둔다.
3. 시장 반응·컨센서스는 "미확인".

## 출력
최종 응답은 구조화 결과만(스키마는 호출 측 `--json-schema`가 강제):
```json
{"results":[{"item_id":"…","level":"P1","event_type":"인증·양산","what":"1문장 요약","impact":"HBM 매출 상향·중 (추정)","reason":"판정 근거 1줄","card_path":"radar/cards/2026/10/R-…yaml"}]}
```
모든 입력 항목에 결과 1개씩. P2·P3는 card_path 생략.
P0·P1에는 `biz`를 채운다: 주인공 기업이 **어떤 사업을 하는 회사인지 1줄**(예: "AI 데이터센터용 광 모듈·레이저 제조", "전력망 송배전 시공"). 아는 사실만 — 모르면 비운다(마스터 지시 2026-10-29).
P0·P1에는 알림 양식(마스터 지시 2026-10-29 "종목｜내용｜시간 → ☞ 회사 설명 3줄 → 핵심 내용 3개")에 들어갈 두 가지도 채운다:
- `points`: 핵심 내용 최대 3줄(각 60자 안팎) — 무엇이 일어났나·숫자(단위 그대로, 금액은 $50.6B·$420M 표기)·왜 중요한가(실적 동인·고객·경쟁). 제목·요약·원문에 있는 사실만, 헤드라인은 주체를 붙인다('로이터 보도'), 확인 전이면 '(미확인)'. 쓸 사실이 적으면 줄 수를 줄인다.
- `profile`: 주인공 기업 설명 3줄 — ① 비즈니스 모델(무엇을 팔아 돈을 버나) ② 성장 동력(지금 매출·이익을 끌어올리는 것) ③ 내러티브(시장이 이 회사를 보는 이야기·멀티플 근거). `config/company_profiles.yaml`에 30일 안의 설명이 있으면 비워 둔다(저장된 것을 쓴다). 확실히 아는 사실만 — 모르면 빈 배열. 매수·매도 표현 금지.

## 금지
- 확인 안 된 내용을 what에 사실처럼 쓰기. 헤드라인 → 사실 금지(금지표).
- local-only 폴더 읽기. 지식 레이어(claims) 직접 수정 — 승격은 claim-intake로.
