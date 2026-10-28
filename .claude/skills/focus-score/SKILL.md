---
name: focus-score
description: 포커스 종목 점수(10점 만점)를 매일 산정한다. AI 밸류체인 유니버스 전 종목의 시장 관심도·내러티브 매력도·펀더멘털 상하방 룸·멀티플 프리미엄을 계산 점수와 모델 판단으로 합성하고, 5.0 이상만 레이더가 추적한다. 변화를 텔레그램으로 보낸다. 예약 작업 chiip-focus-score(매일 06:40) 또는 마스터 요청 시.
---

# focus-score — 포커스 종목 점수 (BUILD_PROMPT §21.13, config/focus.yaml)
목적: 모든 종목을 다 보면 토큰이 낭비된다. **지금 따라갈 가치가 있는 종목**만 고른다. 점수는 '좋은 종목'이 아니라 '지켜볼 이유의 크기'다 — 상방이든 하방이든 크게 움직일 여지가 있으면 높다. 매수·매도 의견이 아니다.

## 절차
1. `py scripts/focus/score.py --prepare` — 엔진 재계산, 요소별 계산 점수(0~10, 없으면 —)와 7일 언급 수 출력.
2. **판단 점수 작성** → `knowledge/models/focus/judgments/YYYYMMDD.csv` (열 `id,component,score,reason,evidence`, 한 요소 한 행).
   - 계산 점수가 없는 요소(가격·추정치 미수집이면 펀더룸·멀티플 전부)는 판단으로 채운다. 계산 점수가 있어도 맥락상 틀리면(예: 언급 수가 수집 원천 구성 때문에 한국 종목에 쏠림) 판단으로 덮고 이유를 쓴다.
   - 근거는 공개 자료만: 최근 실적·가이던스, 공개 보도된 컨센서스 변화, 주가 흐름, 레이더 카드·주장 id, 내러티브 등록부. invest 모드 경계(local-only·필드 인텔 금지).
   - reason은 한 문장, evidence는 카드·주장 id 또는 출처 URL. 근거가 약하면 점수를 중간(4~6)에 두고 reason에 "근거 약함".
   - 전 종목을 매일 다시 쓸 필요는 없다: 전일 판단 파일을 복사해 바뀐 종목만 고친다(어제 이후 실적·가이던스·큰 뉴스·주가 급변이 있었던 종목 우선).
3. `py scripts/focus/score.py --finalize --send` — 합성·변화 계산·포커스 목록(knowledge/models/focus/latest.json, 수집 관문이 읽음)·텔레그램 발송.
4. 알파 점수 보충(어닝 캘린더용, `config/alpha.yaml`): `knowledge/models/earnings/upcoming.json`에서 앞으로 7일 안에 발표하는 종목 중 `knowledge/models/alpha/latest.json`에 점수가 없거나 scored_on이 14일 넘은 종목만 알파 판단을 `knowledge/models/alpha/judgments/<오늘>.csv`에 쓰고 `py scripts/alpha/score.py --finalize`(07~09시 실적 일정 발송 전에 끝나야 한다). 기준은 스킬 tenbagger-card '알파 점수' 절.
5. 노션 대기열: `py radar/telegram_inbox.py --export`에 항목이 있으면(NOTION_TOKEN 없음) 노션 커넥터로 `config/notion.yaml` archive.data_source에 페이지를 만들고 `py radar/telegram_inbox.py --mark-done <ref,...>`. 메모 갱신(status memo_update)은 page_id 페이지의 '마스터 메모'만 고친다.

## 요소 기준 (0~10)
| 요소 | 높음(8~10) | 중간(4~6) | 낮음(0~3) |
|---|---|---|---|
| 관심도 | 주요 매체·X·리서치가 매일 다룸, 주가 변동 큼, 이벤트 임박(실적·제품) | 주 몇 차례 언급 | 거의 언급 없음 |
| 내러티브 매력도 | 확산·컨센서스 단계 핵심 내러티브의 직접 수혜·피해(노출 큼) | 간접 노출 | 연결 내러티브 없음·소멸 |
| 펀더멘털 상하방 룸 | 리비전이 크게 움직이는 중, 가이던스 변곡, 사이클 전환점, 시나리오 폭 넓음 | 완만한 변화 | 추정치 안정·변수 적음 |
| 멀티플 프리미엄 | 피어·역사 대비 극단적 프리미엄 또는 디스카운트(재평가·되돌림 여지) | 피어 수준 | 판단할 근거 없음은 '—'로 두고 쓰지 않는다 |

## 금지
- 점수를 매수·매도·목표주가처럼 쓰기. 출력 끝 `공개 자료 기반 분석이며 투자 권유가 아님`.
- 근거 없이 숫자 채우기 — 모르면 그 요소를 쓰지 않는다(총점은 요소 2개 이상일 때만 나온다).
- 마스터가 always_include로 고정한 종목을 빼는 판단(설정이 우선).
