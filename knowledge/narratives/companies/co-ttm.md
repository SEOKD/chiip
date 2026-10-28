---
id: co-ttm
as_of: 2026-10-28
summary: AI 고다층 PCB 성장주와 부채 큰 보드 제조사 사이의 줄다리기 — 실적일 −30%로 과밀이 풀린 컨센서스 단계(가이던스는 올랐는데 목표가는 내림)
stage: 컨센서스 (과밀 해소 직후)
crowding: 중간
alpha_effect: {gap: +1, upside: 0}
evidence: knowledge/narratives/evidence/co-ttm.json (git 제외 — radar/narrative_sources.py로 재수집)
channels: {community: 10, ib_actions: 21, sector: 5, call_qa: 2개 증권사(원문 일부 잘림), substack: 0, hacker_news: 0}
sectors: [nar-ai-pcb-content, nar-ai-capex-durability]
---
> 근거는 커뮤니티·IB·언론 **헤드라인**(Google News 색인 제목)과 easyconomics 콜 질문 주제(치입 요약, 4개 주제만 확인)다. 시장 기대의 증거이지 사실이 아니다(claim 아님). 숫자는 1차 확인 전 '가이던스(헤드라인·콜 요약 기준)'.

## 섹터 멀티플을 결정하는 내러티브 (AI 서버·네트워킹 PCB)
| 내러티브 | 바뀌는 가치 입력 | 방향 | 근거(채널·대표 제목·날짜) | 단계 |
|---|---|---|---|---|
| AI 서버·스위치의 고다층 PCB 컨텐츠 증가 | TAM, 점유율, 제품 믹스(마진) | 프리미엄 | Celestica 강세 장문 2편(SA 10/23·10/26), "SpaceX AI 인프라 확대 수혜 5종목"(Fool 10/28) | 컨센서스 |
| 데이터센터 프로젝트 **일정** 리스크 | 성장 시점, 위험 | 디스카운트 | Needham "data center timing" 목표가 하향(10/23). 콜에서 Truist가 3분기 데이터센터·네트워킹 매출이 가이던스보다 약 10% 낮은 이유를 물었고, 회사는 고객 프로젝트 일정 탓이라고 답함 | 확산(우려 쪽) |
| 피어 밸류에이션 압축 | 멀티플 | 디스카운트 | Needham "peer valuation compression" 하향(9/21), Stifel "valuation update" 하향(10/23) | 확산 |
| 국방 수주잔고의 안정성 | 위험(할인율) | 프리미엄 | "Priced Like A Board Shop, Booked Like A Defense Prime"(SA 8/25, 1차 수집분), 9/22 부채 조달 AI·국방 인수 발표로 +9.5%(Yahoo) | 태동 |

## 기업 고유 내러티브
**프리미엄 요인**
1. **FY27 예비 전망 첫 제시·가이던스 상향** — "Big Guidance Increase, Cheaper Stock Price"(SA 10/27), 3분기 non-GAAP 이익·매출 증가와 FY27 예비 전망(Yahoo 10/22).
2. **N+M 신제품 비중 확대** — 데이터센터·네트워킹 매출의 약 30%에서 내년 약 50%로(콜 답변, Fox Advisors 질문). 믹스 개선으로 마진이 오를 근거.
3. **아시아 AI 캐파 4억 달러 추가 투자**(TradingView 10/12) — 수요 자신감.
4. **1억 달러 자사주 매입 승인**(TipRanks 10/27).
5. "Wall Street Is Selling A Peak That's At Least Two Years Away"(SA 10/27) — 피크 아웃 우려에 대한 반론.

**디스카운트 요인**
1. **부채 확대**(연이은 인수) — "shares fall amid expanding debt load"(SA 10/22). 콜에서 레버리지, 이자비용의 EPS 부담, 추가 인수 여력, 부채 축소 계획을 질문받음(Fox Advisors).
2. **3분기 데이터센터·네트워킹 매출 가이던스 미달(약 −10%)** — 회사 설명은 고객 일정. 수요 문제인지 일정 문제인지가 내러티브의 분기점.
3. 9/28 급락("Why TTMI Is Nosediving", TradingView), 10/22 하루 −30%(Fool).

## IB 커버리지 흐름 (최근 60일)
| 날짜 | 증권사 | 조치 | 목표가 | 사유(제목 기준) |
|---|---|---|---|---|
| 9/21 | Needham | Buy 유지 | 175달러(하향) | 피어 밸류에이션 압축 |
| 10/11 | (집계) | — | 평균 203달러 | MarketBeat |
| 10/13 | Truist | Buy 유지 | 224 → 231달러 | 성장 전망 |
| 10/23 | Truist | Buy 유지 | 231 → 170달러(−26%) | — |
| 10/23 | Needham | Buy 유지 | 175 → 150달러(−14%) | 데이터센터 일정 |
| 10/23 | Stifel | Buy 유지 | 165달러(하향) | 밸류에이션 갱신 |
- 등급 하향 0건, 실적 후 목표가 하향 3곳("Analysts Cut Their Forecasts Following Q3", Benzinga 10/23). **숫자(가이던스)는 올랐는데 목표가는 내림 = 배수(멀티플) 압축**. 실적 추정 하향인지 배수 하향인지는 리포트 본문 미확인.
- easyconomics `analyst_rating_changes`: 최근 5일 해당 없음.

## 커뮤니티 논조
- **강세**: SA 장문 2편(10/27) — "피크는 최소 2년 뒤", "가이던스는 오르고 주가는 더 싸짐". 논지: AI 보드 수요가 이어지고 N+M 믹스가 마진을 올린다.
- **약세·신중**: Fool "Why TTM Stock Plunged 30% Today"(10/22)·"Plunged This Week"(10/23), SA 뉴스 "debt load"(10/22). 논지: 일정 지연 + 부채.
- 쏠림이 VICR보다 덜하다 — 강세·약세가 맞선다.

## 숫자로 바꾸기 — v2 동인에 주는 의미
- N+M 비중 30% → 50%(회사 답변, 콜 요약 기준, 1차 확인 대기) → 데이터센터 부문 ASP·마진 동인의 상방 근거.
- 부채: 금액·금리 **미확인** → 순부채/EBITDA와 이자비용을 10-Q로 확인해 동인 `net_debt`와 베타 재레버리지에 반영해야 한다. 레버리지가 크면 같은 영업 결과에서도 주주가치 변동폭이 커진다(상하방 모두).
- 실적일 −30%에 FY27 전망 상향이 겹침 → 가격 내포 성장(PIE)이 내려갔을 가능성. 컨센서스 수치가 없어 정량 확인은 못 함(노션 Consensus DB 입력 필요).

## 반증 조건·확인할 KPI
- 4분기 데이터센터·네트워킹 매출이 또 가이던스 미달 → '일정' 내러티브가 '수요' 내러티브로 바뀜(붕괴 쪽).
- N+M 비중이 내년 50%에 도달하는지(분기별 공개 여부 확인).
- 순부채/EBITDA 추세, 차환 조건, 추가 인수 여부.
- 하이퍼스케일러 CAPEX 가이던스(이번 주 빅테크 실적)와 Celestica 3분기 실적(피어 확인).

## 알파 연결 (제안 — 점수 변경은 tenbagger-card '알파 점수' 절에서)
- **gap +1**: 가이던스 상향과 주가·목표가 하락이 엇갈렸다(가격-리비전 괴리). **조건**: 3분기 미달이 고객 일정 문제로 확인될 것.
- **upside 0**: 부채가 주주 몫의 상방을 일부 깎고, 데이터센터 일정 리스크가 남아 있다.
