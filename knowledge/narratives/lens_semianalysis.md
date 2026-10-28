---
id: lens-semianalysis
as_of: 2026-10-28
summary: 알파 점수의 내러티브 판단은 SemiAnalysis 논리 틀로 한다(마스터 지시 2026-10-28 "세미애널리시스의 내러티브 논리를 100% 답습"). 공개 자료로 확인한 방법론만 쓰고 유료 본문은 쓰지 않는다.
used_by: [config/alpha.yaml lens, .claude/skills/tenbagger-card '알파 점수', .claude/skills/narrative-premium]
---
# SemiAnalysis 렌즈 — 알파 점수의 내러티브 판단 규칙

> 근거 범위: SemiAnalysis 공개 제품 설명(Datacenter Industry Model·AI Cloud TCO Model·가속기 모델), 무료 뉴스레터 RSS 제목·부제(`radar/pollers/research_watch.py`가 매일 수집), 공개 인터뷰(Dwarkesh Podcast 2026-03, 2차 보도). **유료(institutional) 본문은 읽지도 인용하지도 않는다**(유료벽 우회 금지) — 방법(원리)을 따르고 결론(유료 산출물)을 복제하지 않는다(BUILD_PROMPT §14).

## 1. 일곱 원리 (공개 근거)
| # | 원리 | SA 공개 근거 | 알파 요소에 쓰는 법 |
|---|---|---|---|
| L1 | **바텀업 공급망 숫자**: 가속기 출하 → 웨이퍼·패키징(CoWoS)·HBM 수요 → 데이터센터 MW(critical IT) → 전력. 내러티브는 반드시 '시스템 출하 × 시스템당 콘텐츠 × 가격'으로 바꾼다 | 가속기 모델·HBM 모델 설명("shipments to wafer starts, packaging volumes, yields, HBM requirements"), Datacenter Industry Model("accelerator shipments translate into power demand") | upside: 이 회사의 시스템당 콘텐츠 증가 × 출하 증가가 컨센서스를 넘는 경로가 숫자로 있는가. 숫자로 못 바꾸면 upside ≤ 5 |
| L2 | **결속 병목(binding constraint)이 가치를 갖고, 병목은 이동한다**: 로직 → 메모리 → 전력 → (2028~29) 리소그래피 | Dwarkesh 인터뷰(로직·메모리·전력 3대 제약, 병목은 공급망 아래로 이동), "Datacenters 2027: +50GW in a Single Year … The Shortage Could Move to Chips"(2026-10-19) | bottleneck: **지금·다음** 결속 병목 보유 = 높음. 해소 쪽으로 가는 병목(공급이 따라잡는 중) = 1점 낮춤. 다음 병목 후보 = 1점 높임 |
| L3 | **TCO가 승자를 정한다**: 성능/달러, 토큰당 비용, GW당 이익. 사양이 아니라 고객 총소유비용 | AI Cloud TCO Model(가속기 시간당 총비용을 줄 단위로), "Vera Rubin NVL72 … 67x better Performance per Dollar"(09-14), "TPU Inference Externalization … Up to 50% Better Performance per Dollar"(09-07), "Why 4-hi HBM Wins"(09-13) | upside·bottleneck: 고객 TCO를 낮추는 제품 = 가산. 고객 TCO를 올리기만 하는 부품(대체·사양 하향 압력, 예: HBM 고단 적층 → 4-hi) = 감산 |
| L4 | **서류·물건으로 검증**: 인허가·부동산 기록·정보공개 청구·위성사진·통관·특허 | Datacenter Model 데이터원 설명, "ASML Is Building a Hybrid Bonding Tool!"(10-15, 특허 출원·로드맵으로 추론) | 모든 요소: 근거가 주장·내러티브뿐이면 '근거 약함'(4~6점). 수주·출하·인허가·특허 같은 물건 증거가 있으면 범위 밖 점수 허용 — 치입 역방향 레이더와 같은 원리 |
| L5 | **통념을 숫자로 반박**: 다들 X라 할 때 숫자가 다르면 반대로 | "Everyone Says Datacenter Moratoriums Are Killing the US Buildout. We disagree"(09-15, 1,525MW만 실제 지연) | gap: 시장 통념(가격에 내포된 걱정)이 바텀업 숫자와 다를수록 높다. 통념과 숫자가 같으면 gap ≤ 5 |
| L6 | **코디자인: 모델·소프트웨어 변화가 하드웨어 TAM을 바꾼다** | "How GLM5.3 Sparse Attention Affects HBM Memory Usage"(09-28), "Engrams … DRAM/SSD Offloading … TAM of DRAM/NVMe"(09-18), "Computation and Data Movement for Inference"(09-21) | upside: KV 캐시 오프로딩·희소 어텐션·MoE 같은 변화가 이 회사 콘텐츠를 늘리면 가산, 줄이면 감산 |
| L7 | **경제성·자금 회의**: AI 클라우드 임대 경제성, 백스톱·금융, 과장된 ARR | "Nvidia's Backstop Universe … Limits of Nvidia's Balance Sheet"(09-11), Nebius ARR 목표 '과도하게 낙관' 제목, "The AI Server Pricing Apocalypse"(제목) | upside: 차입·자본 투입으로 용량을 파는 쪽(AI 클라우드·서버 조립)은 1점 낮춤. 돈을 실제로 버는 병목 보유자가 우선 |

## 2. 크라우딩 규칙 (반대 검증 — 마스터 지시를 따르되 남기는 안전장치)
- SA 리포트는 시장을 움직인다. **SA가 이미 공개적으로(제목·무료 글) 같은 논지를 밀었다면 그 논지는 가격에 반영되기 시작했다** → gap 1점 낮춤. 알파는 SA와 같은 논리로 **SA가 아직 다루지 않은 종목·숫자**에서 나온다(치입 엣지: 한국 공급망·양산 관점·역방향 흔적).
- SA의 결론과 치입 숫자가 다르면 치입 숫자를 쓰고 이유를 적는다(SA도 틀린다 — 'SA도 반대 검증').

## 3. 2026-10-28 현재 적용 (공개 제목 기준)
- 병목 이동: 2027년 데이터센터 +50GW, 부족이 칩으로 옮겨갈 수 있음 → 발전·송배전 쪽 bottleneck −1, 칩 공급망(메모리·첨단 패키징·기판·CCL·테스트·장비·광 레이저) bottleneck +1.
- TCO: ASIC(TPU·Trainium) 외부 판매 확대 — 가속기 다변화는 공급망 전반 물량엔 중립~긍정.
- 경제성 회의: AI 클라우드 용량 판매·서버 조립(Oracle·Dell·Celestica) upside −1.
- 크라우딩: SA 기관 리포트 제목 'xAI 1.9GW 가스터빈 두산 발주' → 두산에너빌리티 gap −1.

## 4. 반증 조건 (렌즈 자체)
- SA 렌즈로 바꾼 뒤 알파 상위군의 6·12개월 초과수익이 렌즈 전보다 낮으면(가상 추적·`model-lab` 주간 검증) 렌즈 가중을 낮춘다 — 마스터에게 보고.
