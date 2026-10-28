---
id: co-vicor
as_of: 2026-10-28
summary: 전력 부품사에서 전력 IP 라이선서로의 재평가(VPD 로열티)가 1순위 내러티브 — 확산 단계, 커뮤니티는 과밀 경계
stage: 확산
crowding: 높음(커뮤니티 강세 쏠림) / 낮음(IB 커버리지 얇음)
alpha_effect: {gap: -1, upside: +1}
evidence: knowledge/narratives/evidence/co-vicor.json (git 제외 — radar/narrative_sources.py로 재수집)
channels: {community: 12, ib_actions: 22, sector: 14, call_qa: 4개 증권사, substack: 0, hacker_news: 0}
sectors: [nar-power-cooling-bottleneck, nar-dc-high-voltage-power, nar-ai-capex-durability]
---
> 근거는 커뮤니티·IB·언론 **헤드라인**(Google News 색인 제목)과 easyconomics 콜 질문 주제(치입 요약)다. 시장 기대의 증거이지 사실이 아니다(레이더 S1·S2급, claim 아님). 숫자는 1차 확인 전 '가이던스(헤드라인·콜 요약 기준)'. 본문을 읽지 않은 기사는 제목만으로 해석했다.

## 섹터 멀티플을 결정하는 내러티브 (AI 데이터센터 전력)
| 내러티브 | 바뀌는 가치 입력 | 방향 | 근거(채널·대표 제목·날짜) | 단계 |
|---|---|---|---|---|
| AI 전력 수요 급증·전력 병목 | TAM, 성장 지속기간 | 프리미엄 | 섹터 14건 중 다수. GE Vernova 수주 급증(Barron's 10/28), 미국 전력 수요 2030년 +20%(Fool 10/24), "AI power crunch 최대 승자" 논쟁(Fool 10/24), 전력주 순위 기사 2건(Fool 10/25·10/28) | 컨센서스→과밀 (순위·'승자 고르기' 기사 범람은 과밀 징후) |
| 고전압·고밀도 전력 구조 전환 | 점유율, 부품 컨텐츠(ASP) | 프리미엄(변환 효율·밀도 기술 보유사) | "The High-Voltage Stopgap That Could Save the AI Buildout"(Barron's 10/28), "Jensen Huang Reveals AI Data Center Quick-Fix"(Barron's 10/22) — **제목만 확인, 랙 내부 전력 구조인지 송전 얘기인지 본문 미확인** | 확산 |
| AI CAPEX 지속성 의구심 | 위험(할인율), 성장 지속기간 | 디스카운트 | "AI Stocks Face Earnings Gut Check As Spending Jitters Mount"(IBD 10/20), "Alphabet Swaps Buybacks for Data Centers. Wall Street Is Getting Nervous"(Barron's 10/28), 메타 데이터센터 채권 약세(Barron's 10/27) | 확산(우려 쪽) |

## 기업 고유 내러티브
**프리미엄 요인**
1. **VPD(수직 전력 공급) 특허 라이선스·로열티** — "부품 회사가 IP 회사로". 9/18 AI 라이선스 계약 뒤 +18%(TIKR), 9/22 매출 전망 상향으로 +19.85%(TradingKey), 10/01 "로열티가 성장 전망을 끌어올림"(Barron's), 10/20 Q4 로열티 4,300만 달러 이상 제시(SA 제목). 콜에서 Needham·Craig-Hallum의 질문이 정확히 여기에 몰렸다: 3분기 로열티의 소급분 비중, 기준선, 단계별 로열티율, 일회성인지 반복인지 → **IB의 초점 = "로열티가 반복 매출인가"**.
2. **2세대 VPD의 주력 고객 밖 채택** — 고객 집중을 풀 수 있는지(콜 질문, Needham·DMB Capital).
3. **Fab-2 증설**(2027년 2분기 장비 단계 반입)과 **Fab-3 부지**(당장 짓지 않는 장기 선택권) — 수요 자신감의 신호. 9/13 신규 팹 시설 인수로 상승(TIKR).

**디스카운트 요인**
1. 3분기 매출 +79%(1억 9,710만 달러, Quiver 10/20)에도 **EPS 미스**(SA 10/20) — 제품 마진·비용 구조 의문.
2. 로열티에 **소급분이 섞여** 기준선이 불확실(콜 질문 1).
3. **IVR(통합 전압조정기) 등 경쟁 기술**로의 대체 가능성(콜 질문, DMB Capital).
4. **주력 고객 집중**(콜 질문 3).

## IB 커버리지 흐름 (최근 60일)
- Needham: Buy 유지, 목표가 320달러(9/22) → 350달러(10/01) → 350달러 재확인(10/20). **상향 방향**.
- "애널리스트 평균 32.8% 상방" 집계 기사(Zacks 계열, 10/08).
- 등급 하향 0건. 콜 질문 증권사 4곳(Needham·Roth Capital·Craig-Hallum·DMB Capital) — 중소형 IB 위주. 대형 IB 커버리지 흔적은 이번 근거에서 **미확인** → 대형 IB 개시가 다음 멀티플 사건 후보.
- easyconomics `analyst_rating_changes`: 최근 5일(도구 한도) 해당 없음.

## 커뮤니티 논조
- **강세(압도적)**: SA 장문 4편 — "시장이 상방을 과소평가"(9/21), "All Roads Lead To Vicor"(10/12), "Buy The Dip In This Key AI Power Enabler"(10/23), "Don't Get Off This Ride"(10/25). Zacks 모멘텀·골든크로스(9/30·10/07). 논지: AI 전력 병목의 핵심 IP, 로열티로 이익 레버리지.
- **약세**: 독립 약세 장문은 이번 근거에서 0건 → **한쪽 쏠림 = 과밀 징후**. 약세 논지는 IB 질문(로열티 반복성·IVR 경쟁)에서만 보인다.
- 가격: 10/07 −7.2%(MarketBeat), 10/20 실적 후 급등(Fool), 10/26 +11%(SA), 10/27 +7.6%(AlphaStreet) — 변동성 큼.

## 숫자로 바꾸기 — v2 동인에 주는 의미
- 로열티 기준선 분기 약 4,300만 달러(회사 제시, 신규 계약 제외 — 콜 요약 기준, 1차 확인 대기) → 연 약 1.7억 달러. 로열티는 원가가 거의 없어 영업이익률·ROIC를 끌어올린다 → 반복성이 확인되면 동인 `ronic_spread`(+)와 장기 마진 페이드 완화의 근거. 확인 전에는 반영하지 않는다.
- 시나리오 확률: 강세(추가 라이선시 + 2세대 VPD 다고객)는 라이선스 계약이 하나 늘 때마다 올리고, 약세(로열티 기준선 하회·IVR 대체)는 4분기 로열티 실적으로 판정한다.
- 멀티플: 선행 P/E 34.9배(알파 1차 판정 수치, 미검증)는 **시장이 이 회사를 부품사로 보느냐 IP 라이선서로 보느냐**에 따라 비싸기도 싸기도 하다. IP 라이선서 피어 대비 비교는 미확인 — 다음 확인.

## 반증 조건·확인할 KPI (멀티플이 바뀔 사건)
- 4분기 로열티가 4,300만 달러 미만이거나 소급분을 빼면 기준선이 낮아짐 → 라이선서 내러티브 약화(멀티플 하향).
- 2세대 VPD 신규 고객 채택 발표·발언(2027년 상반기까지). 없으면 고객 집중 디스카운트 유지.
- Fab-2 장비 반입(2027년 2분기) 지연.
- 추가 특허 라이선스 계약 또는 특허 분쟁 결과.
- 대형 IB 커버리지 개시(프리미엄 확장 사건).
- 주력 고객의 IVR 채택 발언(대체 위험).

## 알파 연결 (제안 — 점수 변경은 tenbagger-card '알파 점수' 절에서)
- **gap −1**: 커뮤니티 강세 쏠림과 급등락 — 로열티 내러티브의 일부는 이미 가격에 들어갔다.
- **upside +1**: 로열티가 반복 매출로 확인되면 마진·ROIC 구조가 바뀌어, v2 기본 가정(RONIC=WACC·마진 페이드)은 과소평가 쪽이 된다.
