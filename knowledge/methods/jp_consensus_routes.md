# 일본 상장사 컨센서스 경로

> 마스터 지시(2026-11-02): "일본 상장회사의 실적을 정리할 때 컨센서스 데이터를 넣을 수 있도록 다양한 경로에서 찾아봐라. 이를 지속적으로 고민하라."
> 이 표는 Laboratory가 매주 일요일 갱신한다(`.claude/skills/model-lab/SKILL.md` weekly). 수집은 `radar/jp_consensus.py`.

## 지금 쓰는 경로 (2026-11-02 확인)
| 순위 | 경로 | 받는 값 | 커버리지 | 쓰는 법 |
|---|---|---|---|---|
| 1 | TradingView 종목 칸 | 지난 분기·다음 분기·다음 회계연도의 매출·EPS 추정, 서프라이즈 | 66곳 중 매출 65곳, EPS 49곳 | `jp_consensus.py` |
| 2 | 보도 인용 시장 예상(市場予想, LSEG·QUICK 표기) | 주로 영업이익 | 건별, 보도된 회사만 | 모델이 건별 검색, 매체·집계처를 함께 적는다 |
| 3 | IFIS 株予報(kabuyoho.jp) | 경상이익 분기 누적·연간 컨센서스, 목표주가 | 건별 | robots `crawl-delay: 72000`(20시간). 자동 수집하지 않는다. 알파 5 이상 종목만 하루 1쪽 |
| 4 | StockAnalysis 공개 페이지 | 올해 연간 매출·EPS 평균·최고·최저, 애널리스트 수 | 건별 | 교차 확인용. 둘째 해부터는 유료 표시라 열지 않는다 |

## 쓰지 않는 경로
| 경로 | 이유 |
|---|---|
| Fiscal.ai 추정·Zacks | 키는 있으나(`XJPX_`) 일본 추정이 없다. 'Data is not yet available', 'No analyst coverage' |
| Easyconomics | 회사 검색이 일본 종목을 찾지 못했다 |
| 민카부 | robots가 ClaudeBot·GPTBot을 전체 금지 |
| 니케이 | robots가 ClaudeBot 등을 금지 |
| 株探 | 무료 표에 시장 예상이 없다. 유료 구역은 열지 않는다 |
| IRBank | 컨센서스 없음 |
| MarketScreener | 자동 접속 403. 우회하지 않는다 |
| 四季報オンライン | 공개 본문이 거의 없다 |

## 아직 못 푼 것
1. **영업이익 est.** TradingView에 칸이 없다. 일본 실적의 핵심 지표라 다음 조사 1순위다.
2. **추정치 품질.** 집계처와 애널리스트 수를 TradingView 칸에서 확인하지 못했다. 소수 애널리스트 값이 섞일 수 있다(예 TOWA EPS est. ¥12.00).
3. **보도 인용값과의 대조.** 같은 분기의 TradingView est.와 보도 인용값 차이를 쌓아 신뢰 범위를 잰다.
4. **회사 공표 컨센서스.** 회사가 IR 페이지에 애널리스트 평균을 올리는 사례가 있는지 찾지 못했다. `jp_ir_docs.py` 자료실 탐색에 'コンセンサス' 문서 감지를 넣을 수 있다.
5. **Yahoo!ファイナンス·Investing.com 일본판.** robots 일반 규칙은 허용. 페이지 구조와 약관을 아직 보지 못했다.

## 주간 점검 절차
- `py radar/jp_consensus.py --coverage`로 커버리지 변화를 본다.
- 위 '아직 못 푼 것'에서 하나를 골라 조사하고 이 파일을 고친다.
- 새 원천은 robots·약관부터 확인한다. 유료벽·로그인·봇 차단은 우회하지 않는다.
- Fiscal.ai 일본 추정 재확인은 `scripts/fiscal/templates/jp_est_check.js`.
