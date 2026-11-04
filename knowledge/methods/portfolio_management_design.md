# Chiip 포트폴리오 매니지먼트 의사결정 설계안 (초안 — 마스터 승인 전)

> 마스터 지시(2026-11-04): "포트폴리오 매니지먼트는 전문성과 경험에 따라 퍼포먼스가 천차만별이다. IB가 쓰는 전문 기법을 적용했으면 한다. 관련 논문과 기술 자료, 전문 서적 등을 조사해 어떻게 매니지먼트 의사결정 과정을 설계하면 좋을지 여러 파라미터와 승수, 변수를 갖고 고민하라."

**경계.** Chiip은 투자자문 자격이 없다. 이 설계가 만드는 것은 **연구용 모델 포트폴리오(가상)**의 비중·위험 지표이며, 마스터 계좌의 매수·매도·비중·금액 지시가 아니다. 마스터 포지션 파일(`portfolio_positions.local.yaml`)은 읽지 않는다. 출력은 "모델 포트폴리오 기준 지표"로만 표기한다.

---

## 1. 왜 바꾸나 — 지금 빠져 있는 고리

| 지금 있는 것 | 빠진 것 |
|---|---|
| 종목 단위 판단: 알파 잠재력, v2 밸류에이션, 시나리오(약세·기본·강세), 단일 종목 분수 켈리(`scripts/valuation/v2/decision.py`, 1/4 켈리) | **종목 사이의 상관** — 같은 AI 전력·패키징 테마 5개가 사실상 한 베팅인지 모른다 |
| 컨빅션 = 방향 적중 확률(2026-11-04 재설계, 보정 대기) | 확률을 **기대수익·비중으로 바꾸는 식** |
| Buy Call·와치리스트 편입·제외 규칙 | **포트폴리오 전체의 위험 예산**(변동성·낙폭·팩터 쏠림·유동성) |
| 보호예수 해제·실적일 일정(`config/portfolio.yaml` events) | **이벤트 전 위험 조정 규칙** |
| 예측 브라이어 점수 | **성과 귀속**: 수익이 종목 선택에서 왔나, 테마 베타에서 왔나 |

실무 근거: 펀더멘털 매니저가 고컨빅션 종목을 체계적으로 **덜 담아** 성과를 깎는다는 실증이 있다. Alpha Theory 2019는 고컨빅션 과대비중 종목이 포트폴리오 비중의 55%로 줄어 있었다고 보고한다. 판단은 맞는데 크기 결정이 그것을 버리는 문제다. 반대로 추정 오차를 무시한 평균-분산 최적화는 극단 비중을 낸다. 아래 설계는 두 실패 사이에서 **"확신만큼 담되, 추정 오차와 상관만큼 깎는"** 구조다.

---

## 2. 의사결정 흐름 — 7단계

```
① 투자 우주 → ② 기대수익(알파) 예측 → ③ 위험 모델 → ④ 포트폴리오 구성 → ⑤ 위험 오버레이 → ⑥ 리밸런싱·체결 → ⑦ 성과 귀속·학습
                     ↑                                                                                         │
                     └──────────────────── IC·브라이어·귀속 결과로 승수 재보정(주·월 단위, 표본 외) ──────────────┘
```

### ① 투자 우주 (Universe)
- 대상: 보유(마스터가 알려준 종목, 비중 정보 없이 '포함' 여부만) + 와치리스트(관심) + Buy Call.
- 관문: 30일 평균 거래대금 ≥ `min_adv_usd`($5M, 기존), 시가총액 ≥ `min_mcap`($300M 사전값), 킬 조건 미발동.
- 변수: `N`(종목 수, 정보 비율 계산의 폭 breadth).

### ② 기대수익 예측 — 세 가지 식을 같이 계산하고 하나로 합친다
1. **확률 가중 수익(Probability-Weighted Return, PWR)** — 펀더멘털 펀드 실무(Alpha Theory 방식).
   `PWR_i = Σ_s p_s · (P_s / P_0 − 1)`, 시나리오 s = 약세·기본·강세(리포트 v2 출력 그대로). `p_s`는 리포트 시나리오 확률.
2. **그리놀드 알파 식**(Grinold & Kahn, *Active Portfolio Management*, 2판 1999).
   `α_i = IC × σ_i × z_i`
   - `z_i`: 표준화한 Chiip 점수(알파 잠재력·컨빅션의 횡단면 z값)
   - `σ_i`: 잔차 변동성
   - `IC`: 정보 계수 — 점수와 이후 수익의 상관. 사전값 0.05, 실무 통상 0.02~0.10
   - 이 식은 점수를 수익률 단위로 바꾸면서 **스스로 축소(shrink)** 한다. IC가 작으면 알파도 작다.
3. **컨빅션 확률 식** — 2026-11-04 재설계한 컨빅션.
   `E_i = p_i · up_i − (1 − p_i) · down_i`
   - `p_i`: 방향 적중 확률(보정식 채택 전에는 사전 사상)
   - `up_i`·`down_i`: 강세·약세 시나리오 폭
- **합치기:** `μ_i = w_pwr·PWR_i + w_g·α_i + w_c·E_i`, 사전 가중치 1/3씩. 세 식이 크게 엇갈리면(부호가 다르면) `μ_i`를 0으로 두고 '판단 충돌'로 표시한다.
- **시장 기대 대비:** v2 역DCF의 가격 내포 성장과 비교한 갭만 알파로 인정한다. 금지표 "시장이 간과했다 → 컨센서스·가격 내포 기대 확인"과 같은 원칙이다.

### ③ 위험 모델 (Risk Model)
- **공분산:** 일간 수익률 252일, EWMA 반감기 63일(RiskMetrics 1996 관행). **레드와·울프 축소**(Ledoit & Wolf 2004, *J. Multivariate Analysis*)로 표본 공분산을 상관 일정 목표로 당긴다. 종목 수가 표본 대비 많을 때 필수다.
- **팩터 노출:** 시장 β(SPY), 규모(IWM−SPY), 모멘텀(MTUM), 섹터 ETF, 그리고 Chiip 고유의 **테마 팩터 3개** — AI 반도체(SMH), 전력 인프라(GRID·PAVE), 원자력·우주(URA·ITA). 회귀 252일.
  - 이미 `config/midterm2026.yaml`에 ETF 바스켓과 β 회귀 엔진이 있어 재사용할 수 있다.
- **고유 위험:** 잔차 변동성 σ_ε. 실적일·보호예수 해제일이 낀 기간은 이벤트 분산을 더한다: `σ²_event = (과거 실적일 |수익| 평균)²`.
- **꼬리:** 역사적 CVaR 95%(1일·5일). 정규분포를 가정하지 않는다.

### ④ 포트폴리오 구성 (Construction) — 기준선 2개 + 본 모델 1개
- **기준선 A — 동일 위험(Risk Parity·역변동성):** `w_i ∝ 1/σ_i`.
  - Maillard, Roncalli & Teiletche 2010(*JPM*)의 위험 기여 균등화(ERC)를 상관까지 반영한 판.
  - 판단 없이 위험만 나눈 비교 대상이다. 본 모델이 이것을 못 이기면 판단이 가치를 더하지 못하는 것이다.
- **기준선 B — 계층적 위험 균형(HRP):** López de Prado 2016(*JPM*).
  - 상관으로 군집(같은 테마)을 묶은 뒤 위험을 나눠, 공분산 역행렬 없이 안정적이다.
  - 같은 테마 쏠림을 자동으로 막는다.
- **본 모델 — 블랙-리터만(Black & Litterman 1992, *FAJ*) + 제약 평균-분산:**
  - 사전 기대수익 `Π = λ·Σ·w_mkt`(우주의 시가총액 비중 = 시장 균형).
  - Chiip 견해 `Q = μ_i`(②). 견해 불확실성 `Ω_ii = (1/c_i − 1)·τ·σ²_i`, `c_i`는 컨빅션 확률을 0~1로 펼친 값(Idzorek 2005의 확신도 → Ω 변환). **컨빅션이 낮으면 견해가 시장 균형 쪽으로 자동 축소된다.**
  - 사후 기대수익 `μ_BL` → 최적화: `max w'μ_BL − (λ/2)·w'Σw − κ·|w − w_prev|`
  - 제약: 단일 종목 ≤ `w_max`, 테마(군집) ≤ `theme_max`, 종목 비중 ≤ `adv_frac` × 30일 거래대금 환산, 롱 온리, 현금 허용.
- **크기 상한(사이징):** 각 종목의 최종 비중은 `min(BL 비중, k_kelly × f*_i, w_max)`.
  - `f*_i`는 기존 v2 단일 종목 켈리. 분수 켈리 근거는 MacLean, Thorp & Ziemba 2011(*The Kelly Capital Growth Investment Criterion*). 추정 오차를 감안하면 완전 켈리는 과도하다.

### ⑤ 위험 오버레이 (Risk Overlay)
- **변동성 목표(volatility targeting):** 포트폴리오 예상 변동성이 `σ_target`을 넘으면 전체 노출을 `σ_target/σ̂`로 줄인다(현금 비중 증가).
  - 근거: Moreira & Muir 2017(*J. Finance*) "Volatility-Managed Portfolios" — 변동성이 높을 때 줄이면 위험 조정 수익이 개선됐다.
- **낙폭 제어(drawdown control):** 노출 상한 `= 1 − DD_now / DD_max`.
  - 근거: Grossman & Zhou 1993(*Mathematical Finance*). 고점 대비 낙폭이 커질수록 노출을 기계적으로 줄여 최대 낙폭을 묶는다.
- **이벤트 위험 할인:** 실적일 D-3~D+1, 보호예수 해제일 D-5~D+3에는 해당 종목 목표 비중 × `event_haircut`.
  - 마스터 보유 종목의 IPO 보호예수(EROC 12/7, INIO 12/1, CBRS 11/9)를 이미 일정에 갖고 있다.
- **팩터·테마 쏠림 한도:** 테마 팩터 노출 합 ≤ `factor_max`. 시장 β는 `beta_band` 안.
- **유동성 스트레스:** 비중 × 포트 규모 / (30일 거래대금 × `liq_days`) ≤ 1. 5일 안에 청산 가능해야 한다.
- **킬 조건(테제 붕괴):** 리포트의 반증 조건이 발동하면 가격과 무관하게 목표 비중 0.
  - 가격 손절은 쓰지 않는다. 낙폭 제어가 포트 단위로 대신한다(테제 기반 투자와 손절 규칙의 충돌을 피한다).

### ⑥ 리밸런싱·체결
- **무거래 구간(no-trade band):** 목표와 현재 차이가 `band` × 목표 비중 이하이면 거래하지 않는다.
  - 근거: Gârleanu & Pedersen 2013(*J. Finance*) — 거래비용이 있으면 목표 쪽으로 '일부만' 움직이는 것이 최적이다(조정 속도 `a`).
- **새 정보 트리거:** 인사이트 7 이상 + 컨빅션 변동이 큰 Pulse 건이 나오면 그 종목만 재계산한다. 정기 재계산은 주 1회(월요일 KST 07시, 미국 장 전).
- **체결 비용 모형:** 스프레드/2 + 시장 충격 `η·σ·√(주문량/일 거래량)`.
  - 근거: Almgren & Chriss 2000의 제곱근 충격 법칙, 실무 통상.
  - 가상 포트이므로 성과 계산에서 비용을 차감할 때만 쓴다.

### ⑦ 성과 귀속·학습 (Attribution & Learning)
- **브린슨 귀속**(Brinson, Hood & Beebower 1986, *FAJ*): 테마 배분 효과와 종목 선택 효과로 나눈다.
- **팩터 귀속:** 수익 = Σ β_k·f_k + 잔차. 잔차가 Chiip의 실제 알파다. "AI 테마가 올라서 번 돈"을 선택 능력으로 착각하지 않는다.
- **판단 품질:**
  - 실현 IC: 점수와 다음 20거래일 잔차 수익의 순위 상관, 월별.
  - 컨빅션 브라이어 점수.
  - 적중률 × 손익비.
- **전략 검증:**
  - 수축 샤프(Deflated Sharpe Ratio, Bailey & López de Prado 2014, *JPM*): 여러 번 시도한 끝의 샤프가 운인지 가른다.
  - 최소 트랙 레코드 길이: 같은 저자들의 MinTRL. 그 전에는 "판정 불가"로 쓴다.
- **기본 법칙 점검:** `IR ≈ IC × √N × TC`(Grinold; 전이 계수 TC는 Clarke, de Silva & Thorley 2002, *FAJ*). 제약이 판단을 얼마나 깎는지(TC)를 매월 잰다.

---

## 3. 파라미터·승수·변수 표 (모두 사전값 — 등록부 등록 후 표본 외로만 조정)

| 기호 | 뜻 | 사전값 | 범위 | 근거 | 조정 방법 |
|---|---|---|---|---|---|
| IC | 점수→수익 정보 계수 | 0.05 | 0.00~0.10 | Grinold & Kahn 실무 통상 | 실현 IC 12개월 이동 평균, 축소 추정 |
| w_pwr, w_g, w_c | 기대수익 세 식 가중 | 1/3씩 | 합 1 | 사전 동일 가중(모형 불확실성) | 식별 표본 외 IC 비율 |
| λ | 위험 회피 계수 | 2.5 | 1~5 | 시장 균형 역산 관행(BL 문헌) | 고정(위험 정책) |
| τ | BL 사전 불확실성 | 0.05 | 0.01~0.1 | He & Litterman 1999 | 고정 |
| c_i → Ω | 컨빅션 → 견해 신뢰 | Idzorek 변환 | — | Idzorek 2005 | 컨빅션 보정식 채택 시 연동 |
| k_kelly | 분수 켈리 | 0.25 | 0.1~0.5 | MacLean·Thorp·Ziemba | 고정(기존 config와 같음) |
| w_max | 단일 종목 상한 | 10% | 5~15% | 집중 펀드 관행 | 고정 |
| theme_max | 테마(군집) 상한 | 35% | 25~50% | HRP 군집·실무 | 고정 |
| σ_target | 연 변동성 목표 | 20% | 15~30% | 소형 성장주 우주 기준 | 고정(위험 정책) |
| DD_max | 허용 최대 낙폭 | 25% | 15~35% | Grossman–Zhou | 고정 |
| event_haircut | 이벤트 전 비중 승수 | 0.7 | 0.5~1.0 | 실적일 분산 비율 | 과거 실적일 |수익| 분포 |
| beta_band | 시장 β 범위 | 0.8~1.3 | — | 롱 온리 성장 | 고정 |
| factor_max | 테마 팩터 노출 합 | 1.5 | 1~2 | 실무 | 고정 |
| adv_frac / liq_days | 유동성 한도 | 10% / 5일 | — | 실무 | 고정 |
| band | 무거래 구간 | 20% | 10~30% | Gârleanu–Pedersen | 회전율·비용 표본 외 |
| a | 목표 쪽 조정 속도 | 0.5 | 0.2~1 | Gârleanu–Pedersen | 같음 |
| η | 시장 충격 계수 | 0.5 | — | Almgren–Chriss 실무 | 고정 |
| EWMA 반감기 | 공분산 기억 | 63일 | 21~126 | RiskMetrics 관행 | 표본 외 공분산 예측 오차 |
| shrink δ | 레드와·울프 축소 강도 | 해석해(자동) | 0~1 | Ledoit–Wolf 2004 | 자동 |

**과적합 방지 원칙**
1. 위험 정책 상수(λ·w_max·σ_target·DD_max·k_kelly)는 **피팅하지 않는다.** 정책이지 추정치가 아니다.
2. 추정 상수(IC·가중·반감기·band)만 조정한다. 표본 외 6개월 이상, 수축 샤프 > 0일 때만 바꾼다. 상대 변화 20% 이상은 마스터 승인.
3. 매번 기준선 A·B와 비교한다. 본 모델이 두 기준선을 표본 외에서 이기지 못하면 본 모델의 복잡도를 늘리지 않는다.

---

## 4. Chiip 기존 부품과의 연결

| 단계 | 재사용 | 새로 만들 것 |
|---|---|---|
| ① 우주 | `scripts/portfolio/watchlist.py`, `buy_call.py`, 거래대금 관문 | — |
| ② 기대수익 | v2 시나리오·몬테카를로(`scripts/valuation/v2/`), 컨빅션 `conviction2`, 알파 잠재력 | `scripts/pm/expected.py`(세 식 합성·충돌 표시) |
| ③ 위험 | `radar/markets/midterm.py`의 β 회귀·ETF 바스켓 | `scripts/pm/risk.py`(EWMA·레드와·울프, 테마 팩터) |
| ④ 구성 | v2 켈리 `decision.kelly` | `scripts/pm/construct.py`(역변동성·HRP·BL, 표준 라이브러리만) |
| ⑤ 오버레이 | `config/portfolio.yaml` events(실적·보호예수), 킬 조건 | `scripts/pm/overlay.py` |
| ⑥ 리밸런싱 | Pulse 인사이트·컨빅션 트리거 | `scripts/pm/rebalance.py`(무거래 구간) |
| ⑦ 귀속 | 성과 원장들(`score_ledger`, `rating_ledger`, `watchlist_log`) | `scripts/pm/attribution.py`(브린슨·팩터·IC·DSR) |

- 데이터: 일봉은 Fiscal.ai 1순위·TradingView 보조(한 번에 하나씩). 새 패키지 없이 표준 라이브러리로 쓴다. 필요하면 numpy 승인을 따로 요청한다.
- 출력: Portfolio 데일리에 `■ 모델 포트폴리오 지표` 절 하나. 담는 지표는 아래와 같고, 매매·비중 지시 문구는 쓰지 않는다.
  - 예상 변동성·낙폭·β·테마 노출
  - 이벤트 할인 대상
  - 기준선 대비 성과

---

## 5. 단계 계획

| 단계 | 내용 | 완료 기준 |
|---|---|---|
| 1 | 위험 모델 + 기준선 A·B + 오버레이 지표(변동성·테마 쏠림·이벤트) | 실제 데이터로 공분산·β 산출, 테스트 통과 |
| 2 | 기대수익 합성 + 블랙-리터만 + 분수 켈리 상한 | 세 식 충돌 표시, 견해 축소 확인 |
| 3 | 가상 포트 일일 장부 + 무거래 구간 + 비용 | 회전율·비용 차감 성과 |
| 4 | 귀속·IC·DSR 월간 성적표, 추정 상수 재보정 관문 | 표본 외 6개월 뒤 첫 판정 |

---

## 6. 참고 문헌 (서지는 기억 기반 — 원문 대조는 구현 단계에서 등록부 source로 확인)
- Grinold, R. & Kahn, R. (1999). *Active Portfolio Management*, 2nd ed. McGraw-Hill.
- Black, F. & Litterman, R. (1992). Global Portfolio Optimization. *Financial Analysts Journal* 48(5).
- He, G. & Litterman, R. (1999). The Intuition Behind Black-Litterman Model Portfolios. Goldman Sachs.
- Idzorek, T. (2005). A Step-by-Step Guide to the Black-Litterman Model.
- Ledoit, O. & Wolf, M. (2004). A well-conditioned estimator for large-dimensional covariance matrices. *J. Multivariate Analysis* 88(2).
- Maillard, S., Roncalli, T. & Teiletche, J. (2010). The Properties of Equally Weighted Risk Contribution Portfolios. *J. Portfolio Management* 36(4).
- López de Prado, M. (2016). Building Diversified Portfolios that Outperform Out of Sample. *J. Portfolio Management* 42(4).
- MacLean, L., Thorp, E. & Ziemba, W. (2011). *The Kelly Capital Growth Investment Criterion*. World Scientific.
- Moreira, A. & Muir, T. (2017). Volatility-Managed Portfolios. *J. Finance* 72(4).
- Grossman, S. & Zhou, Z. (1993). Optimal Investment Strategies for Controlling Drawdowns. *Mathematical Finance* 3(3).
- Gârleanu, N. & Pedersen, L. (2013). Dynamic Trading with Predictable Returns and Transaction Costs. *J. Finance* 68(6).
- Almgren, R. & Chriss, N. (2000). Optimal Execution of Portfolio Transactions. *J. Risk* 3(2).
- Brinson, G., Hood, L. & Beebower, G. (1986). Determinants of Portfolio Performance. *Financial Analysts Journal* 42(4).
- Clarke, R., de Silva, H. & Thorley, S. (2002). Portfolio Constraints and the Fundamental Law of Active Management. *Financial Analysts Journal* 58(5).
- Bailey, D. & López de Prado, M. (2014). The Deflated Sharpe Ratio. *J. Portfolio Management* 40(5).
- J.P. Morgan/Reuters (1996). *RiskMetrics — Technical Document*.
- 실무 자료: Alpha Theory, "The Active Manager Paradox: High-Conviction Overweight Positions"(2019, 블로그) · "Fundamental Optimization"(블로그) · Cambridge Associates, "Improving Investment Returns: Manager Sizing With Active Risk"(2020).
