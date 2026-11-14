# ADR-040 — 계속가치 RONIC을 리포트 해자 판정과 잇는다(2026-11-15)

마스터 승인(2026-11-15 "Yes, go ahead"): ADR-039에서 남긴 '계속가치 RONIC을 해자 판정과 잇는 고도화'를 진행.

## 문제
- v2 DCF 계속가치는 RONIC = WACC(11년차 이후 성장은 가치를 더하지 않는다 — 맥킨지 보수 가정)가 기본이고, 해자로 RONIC을 올리는 장치(D6)는
  있었지만 해자 점수(`moat_score`)를 채우는 곳이 없어 동인에 `ronic_spread`를 손으로 적은 4종목만 켜졌다.
- 한편 Analysis 리포트는 종목마다 해자를 근거와 함께 판정한다(`datapack.moat.items` — 유형·판정·주장·근거·수치·반증, 78종목 285건). 이 판정은
  멀티플 선정의 해자 프리미엄에만 쓰이고 DCF에는 들어가지 않았다.
- 출구 배수 점검(D5)의 업종 범위(반도체 8~25배 등)는 '어림값, 대조 전'이었고, 보수 가정이 낳는 낮은 출구 배수를 '범위 밖'으로 띄웠다(122종목 중 71곳).

## 결정
1. **해자 점수**(`plus.moat_score`): 근거(evidence)가 있고 판정이 확인된 항목만 센다. 점수 = clip(Σ 판정 점수 ÷ 상한, 0, 1) — 점수표는 멀티플 선정과
   같은 `config/tenbagger.yaml multiple_select.moat_points`(강함 0.04·보통 0.015·약함 −0.015)·`moat_cap` 0.12를 한 곳에서 읽는다.
   강함 3개 = 1(넓은 해자), 강함 1·보통 2 = 0.58(좁은 해자), 보통 2 = 0.25. 같은 뜻 다른 표기(중간 → 보통, 약점·약화 중 → 약함)를 정리하고,
   멀티플 선정도 같은 정리를 쓴다(11/15 점검: 10건이 점수표에 없어 0점이었다).
2. **RONIC = WACC + max_spread(0.08, prm-dcf-roic-maxspread) × 해자 점수** — 동인에 `ronic_spread`가 있으면 그것이 우선(손으로 적은 1차 근거).
3. **10년차 ROIC 상한**(`dcf.effective_ronic`): 해자에서 온 RONIC은 max(WACC, 10년차 ROIC)를 넘지 않는다. 기존 자본으로 자본비용도 못 버는 회사가
   새 투자에서만 넓은 해자 수익을 낸다고 둘 수 없다(LTH: 해자 판정은 넓지만 10년차 ROIC 9.0% < WACC 9.3% → RONIC = WACC 그대로).
4. **이중 반영 방지**: 멀티플 선정의 펀더멘털 조정(합리적 멀티플)은 해자를 뺀 DCF(RONIC = WACC)로 잰다(`multiples.analyze`). 동종 내재 배수도
   RONIC = WACC로 계산되므로 같은 기준이 되고, 해자는 해자 프리미엄으로 한 번만 들어간다. 목표주가의 DCF 요인·등급 교차 확인은 해자를 넣은 DCF를 쓴다
   (요인끼리는 가중 평균이라 같은 근거가 여러 요인에 들어가도 더해지지 않는다).
5. **출구 배수 점검 재보정**: 위 기준 = 업종의 지금 EV/EBIT(Damodaran, US, 2026-01, 이익 양수 기업 — `valuation_v3.yaml exit_check.industry_ev_ebit`,
   동인 업종 21개 대응). 10년 뒤 안정 성장 해의 출구 배수가 지금 업종 배수(성장 기대 포함)보다 높으면 '공격적' 경고. 아래 기준은 (1 − t)/WACC
   (성장이 가치를 더하지 않는 바닥 — RONIC ≥ WACC면 그 밑으로 못 간다)라 낮다고 경고하지 않는다. 금융업(소송 금융)은 EV 배수가 맞지 않아 점검하지 않는다.

## 근거
- McKinsey(Koller·Goedhart·Wessels) Valuation 7판 — 계속가치 가치 동인 공식, RONIC = WACC는 경쟁 업종의 기본, 지속 가능한 우위(특허·브랜드)가 있으면 RONIC > WACC.
- McKinsey Quarterly "A long-term look at ROIC"(2006) — 미국 상장사 중앙 ROIC는 장기 자본비용과 비슷하고, 진입 장벽이 있는 업종(제약·소비재)은 높은 ROIC가 오래 간다.
- Fama & French(2000) 수익성 평균회귀 — 해자 스프레드 상한을 한 자릿수(8%p)로 두는 근거(prm-dcf-roic-maxspread).
- Damodaran, Enterprise Value Multiples by Sector (US), Data as of January 2026 — https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/vebitda.html

## 효과(122종목, 2026-11-15)
- RONIC > WACC 종목: 리포트 해자로 71곳 + 동인 명시 4곳. 해자 판정은 있으나 10년차 ROIC 상한에 걸려 RONIC = WACC 5곳(LTH 등), 해자 점수 0 1곳, 해자 판정 없음 41곳. 기본 DCF가 바뀐 종목 71곳, 바뀐 종목의 중앙 +5.7%. 전체 기본 DCF ÷ 시총 중앙 0.694 → 0.718.
- 많이 바뀐 곳은 계속가치 비중과 차입이 큰 종목(FRVO +66%, 코어위브 +47%, Riot +25%, CACI +23%, 코닝 +22%).
- 최근 리포트 종목 기본 DCF: APP −14% → −6%, 엔비디아 +11% → +17%, 오라클 −29% → −17%, CBRS −36% → −34%, LTH −69%(그대로, ROIC 상한), AMAT −32%(그대로, 동인 명시).
- 출구 배수 경고 71 → 0(지금 업종 배수를 넘는 공격적 계속가치 없음). DCF 신뢰 점검 정상 116 · 주의 4 · 산정 불가 2(ADR-039와 같음).
- 이미 낸 리포트는 다시 내지 않았다(목표주가·등급 변경은 마스터 판단). 다음 렌더부터 반영.

## 남긴 것
- 해자 스프레드 상한 0.08과 점수표는 사전값 — 리포트 원장의 실현 성과가 쌓이면 표본 외로 검증(prm-dcf-roic-maxspread fit).
- Damodaran 업종 배수는 연 1회(1월) 갱신 — model-lab 월간 점검에 넣는다.
- 업종 대응 중 근사(데이터센터 → Computer Services, 결제 → Business & Consumer Services 등)는 표기만 하고 대조 전.
