# Chiip Ten-bagger Discovery — IB 리서치 하우스식 발굴·의사결정 절차

> 마스터 지시(2026-10-29): "Taiyo Yuden, JX Advanced Metals, Nitto Boseki, Yageo, Union Tool 같은 엣지 있는 AI 밸류체인 종목을 발굴하는 데 집중하라. 발굴하고 관련 보도(반드시 원문)를 팔로업하고 실적도 챙기고 텐배거 리포트도 적어라. 투자 커뮤니티 관심도를 트래킹하고 글로벌 IB 리서치 하우스의 전통적이고 독보적인 접근 방법과 의사결정 과정을 답습해 발굴 역량을 갖춰라."
> 구현: `config/discovery.yaml`(테마·후보·가중치) · `radar/attention.py`(관심도) · `scripts/discovery/screen.py`(선별·편입) · `config/coverage.yaml`(커버리지) · 대만 `radar/pollers/tw_disclosure.py` · 일본 `jp_disclosure.py`·`jp_ir_qa.py` · Chiip Ten-bagger 일요일 발굴 회차(`docs/tasks/chiip-tenbagger.md` 5번).

## 글로벌 IB 리서치의 공통 관행을 옮긴 것 (특정 하우스의 내부 절차를 안다고 주장하지 않는다 — 공개적으로 알려진 일반 관행)
1. **테마 → 병목 → 함량(content per unit)**: 셀사이드 반도체·부품 팀은 최종 제품(AI 서버·가속기 보드·스위치)을 분해해 부품별 '대당 함량 × 출하'로 수요를 세운다. 이익은 공급이 막힌 곳(소수 공급사·긴 증설 리드타임·인증 장벽)에 몰린다 → `themes[].bottleneck·driver`.
2. **두 번째 파생 수혜(second-derivative)**: 1차 수혜(GPU)보다 덜 알려진 공급망 깊은 곳(유리섬유 천·드릴 비트·타깃·프로브 카드)에서 가격 결정력이 더 오래간다 → 후보는 일부러 대형 1차 수혜주보다 깊은 층에서.
3. **아시아 공급망 데이터 추적**: 대만 월매출(매월 10일 전후, 세계에서 가장 빠른 공급망 실적), 일본 적시공시·결산설명회 Q&A, 한국 수출 통계 — 셀사이드 아시아 팀의 기본 도구 → `src-twse-monthly`·`src-tw-disclosure`·`src-jp-disclosure`·`src-jp-ir-qa`.
4. **커버리지 공백(under-followed)**: 애널리스트 수가 적은 종목에서 정보 비효율이 크다. 셀사이드가 '커버리지 개시'를 하면 관심이 붙는다 → `coverage_gap` 가점, 그리고 **IB 행사 초청 공시**(증권사 투자자 콘퍼런스·법인설명회)를 관심의 선행 신호로 센다(`sellside_events`).
5. **변이 관점 + 촉매 일정(variant perception & catalysts)**: "시장은 무엇을 믿고 있고, 우리는 무엇을 다르게 보며, 언제 무엇으로 확인되나" — 날짜가 붙은 촉매 없이는 편입하지 않는다.
6. **종목 선정 위원회(stock selection committee) 메모**: 리서치 헤드·섹터 애널리스트가 한 장 메모로 토론해 '커버리지 개시/관심 목록/보류'를 정한다. 반대 논리를 맡는 사람(devil's advocate)이 있다 → 치입은 `red-team` 서브에이전트가 그 역할.
7. **포지션 크기는 확신도·하방으로**: 의견 등급 대신 치입은 지표(확신도·하방·P(≥2·3·10배))만 — 투자자문 아님.

## 단계와 관문 (`scripts/discovery/screen.py`)
| 단계 | 관문(통과 조건) | 산출 |
|---|---|---|
| ① 아이디어 | 테마 지도(`config/discovery.yaml`)에 있음 — 병목·함량 동인·확인 자료가 적혀 있어야 | 후보 행 |
| ② 선별 | 점수 ≥ 6.0, edge ≥ 6, 펀더멘털 확보(easyconomics) | 순위표 `outputs/discovery/<날짜>.md` |
| ③ 심층 대기열 | 선별 통과·미커버 상위 3 | — |
| ④ 위원회 메모 | **원문 증거 2개 이상**(회사 공시·결산 자료·IR Q&A·고객/공급사 공시, 2차 보도 단독 불가) + 변이 관점 + 날짜 붙은 촉매 + 킬 조건 + 멀티플(동종 레인지·할인 분해) + red-team 반론 | `knowledge/models/discovery/memos/<날짜>_<id>.md` |
| ⑤ 커버리지 | 메모 결론 focus/bench → `py scripts/discovery/screen.py --promote <id> --stage focus --memo <경로>` | `config/coverage.yaml` + 리포트 대기열 |

선별 점수(가중치 `scoring`, 사전값 — 성과로 피팅): 병목 대체 불가성 edge 0.30 · 매출 성장 0.15 · 커버리지 공백 0.10 · 관심 가속 0.15 · 쏠림 −0.10 · 테마 내 밸류(EV/매출 ÷ 성장) 0.15 · 텐배거 시가총액 구간 0.15.

## 투자자 관심도 (`radar/attention.py`)
- **가속이 수준보다 중요하다**: 오늘 7일 언급 수 ÷ 직전 4주 같은 원천 평균. 관심이 가격보다 먼저 붙는 구간을 찾는다(투자자 주의 문헌: Da, Engelberg & Gao 2011 *Journal of Finance* — 검색량으로 잰 관심이 단기 가격 압력·이후 반전과 연결).
- **쏠림은 감점**: 관심 절대 수준이 후보 중 상위면 이미 알려진 이야기(SemiAnalysis 렌즈의 크라우딩, 같은 논지를 SA가 밀었으면 gap −1).
- 원천: 글로벌 언론(영문명)·현지 언론(일본어·중국어·한국어명)·Seeking Alpha·Substack(색인 제목)·공개 리서치 RSS·IB 행사 초청 공시·레딧(미국 티커). **X·텔레그램은 CLAUDE.md 제외 원천이라 꺼져 있다** — 마스터가 허용하면 공식 API·공개 채널의 회사명 언급 수만(본문 저장 없음).

## 커버리지 편입 후 자동 연결
- 원문 팔로업: 일본 적시공시 미러·IR Q&A(`config/jp_watch.yaml`·`config/jp_ir.yaml`에 추가), 대만 重大訊息(`tw_disclosure` — 테마 후보·커버리지 대만 종목 전부), 대만 월매출, 미국 SEC.
- 실적: 발표 시 Dean's Ticker 3단 양식(`knowledge/methods/earnings_format.md`).
- 텐배거 리포트: `pick_report.py`가 커버리지 focus를 알파 순위보다 먼저 고른다(30일 안 재작성 금지).
- 성적표: 편입일 가격·시가총액을 `knowledge/models/tenbagger/watch.csv`에, 월 1회 기저율 대비 성과 → 가중치 피팅(`model-lab`).
