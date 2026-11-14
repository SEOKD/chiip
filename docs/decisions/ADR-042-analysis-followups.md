# ADR-042 — Analysis 양식 후속: 시세·동인 동기·해자 기준선·동종 규모·가이던스 해(2026-11-15)

마스터 지시(2026-11-15): "Yes, continue" — ADR-041 '남긴 것'을 이어서 한다.

## 고친 것
| 영역 | 문제 | 고침 |
|---|---|---|
| 시세 파일 | 77/96곳이 시세 파일 없이 datapack 스냅숏 가격을 썼다 | `prices_free.py --tv-symbols`(동인 있는 종목 → TradingView 기호, tradingview_symbols.csv → datapack companyKey 순) · `--tv-put <json> --date`가 `prices/<종목 id>.csv`에 종가를 쓴다. `run.resolve_market`이 더 새 가격을 쓴다. 122곳 11/13 종가로 채움 — 중앙 가격 나이 2일, 7일 넘는 곳 0. 리포트 회차 첫 단계로 적었다(docs/tasks/chiip-tenbagger-report.md) |
| 수기 동인 | 손으로 만든 동인 5곳이 datapack 갱신을 따라가지 않았다(AMAT 순차입 −6.76 vs −2.01) | `run.sync_warns`: auto 아닌 동인의 주식 수(1% 넘게)·순차입(리스 자본화 몫 빼고 시총의 1% 넘게)을 datapack 자동 동인과 대조해 DCF 신뢰 점검 경고로, 상태 '정상' → '주의'. `market.why`가 있으면 이유가 적힌 것으로 본다 |
| 해자 프리미엄 | 동종도 해자가 있어 동종 중앙값에 이미 들어 있는데 해자 점수를 절대값으로 더했다 | `multiple_select.moat_baseline` 0.055(등록부 prm-tb-mult-moat-base, 사전값) — 해자 점수 합에서 빼고 상한으로 자른다. 해자 항목이 없으면 빼지 않는다 |
| 동종 규모 | 12/66곳 동종 중앙 시총이 대상의 5배 초과, 판단 조정으로 메웠다 | `datapack_check` '동종 규모': 시총 있는 동종의 절반 이상이 대상 시총(기본 주식 × 가격)의 0.2~5배가 아니면 경고 — 동종을 바꾸라는 신호(점수 밖 경고) |
| 가이던스 해 | 가이던스와 컨센서스 첫 해가 다른 해·기준일 수 있다(CBRS 0.95 vs 0.885, MTD FY2025 키, MVIS −10%) | `build_drivers.build`: 가이던스 중간값이 컨센서스 첫 해와 5% 넘게 다르고 `guidance.basis_note`가 없으면 출처 칸에 경고 |

## 남긴 것
- LOTTEEM unit_usd 10⁹ 오류 — 맞는 값을 확인하지 못해 고치지 않았다.
- 원화 환율 단일 표, 강세·약세 ±25%를 동종 분산으로.
- 해자 기준선 0.055는 운영 가정 — 해자 구간별 표본 외 초과수익으로 피팅한다.
- 이미 낸 리포트는 다시 내지 않았다.
