# ADR-032 Quantral → Valuation Queue — 커뮤니티 관심을 알파·내러티브·동인·Analysis에 잇고, 읽히지 않던 출력을 맥락 묶음으로 (2026-11-14)

## 맥락
마스터 지시(2026-11-14, Build Prompt 세션 전달) "Quantral → Valuation Queue 작업 재개". 조건: 커뮤니티 자료는 Quantral MCP로만, 작성자·본문·링크 없이 sourceType·detectedAt만 저장. 적용 4곳(알파 점수·내러티브·동인 notes·Analysis 커뮤니티 반응). 읽히지 않던 출력(social_surge·ib_actions·CPI/PPI/한국 수출·IPO 감시) 연결. 헤드리스 호출 가능 여부 확인.
점검(2026-11-13~14)에서 드러난 것:
- 알파 v1(`scripts/alpha/score.py` attention)·v2(`config/alpha_v2.yaml` attention 블록 social_z)는 이미 `radar/social_surge.py` 집계(Quantral)를 쓴다.
- 그러나 Valuation Queue 지시문은 social_surge·ib_actions·거시 지표·IPO 감시를 읽지 않았다. 데이터 허브(`gather.py`)에도 없었다.
- Pulse 2-1이 Quantral 원응답(작성자 적중률·감성·링크 포함)을 `radar/state/quantral_in.json`에 저장한 채 남겼다(git 제외지만 조건 위반).
- Quantral 주간 W46 출력은 개발 중 시험본(as_of '시험')이다.

## 결정
1. **맥락 묶음** `scripts/valuation/v2/queue_context.py`(결정론):
   `--company <id>` = Quantral 관심(급증 Z·관심 점수·알파 관심 요소·채널별 최근 건수·과밀) + Quantral 주간 리테일 순위(시험본 제외) + IB 커버리지 장부 최근 3건.
   `--market` = 미국 PPI·CPI 최근 발표(개정 포함) + 한국 반도체 수출(공백 이유 포함) + IPO 감시 상태. `--note <id>` = 동인 notes·내러티브용 한 줄.
   데이터 허브 원천으로 등록: 종목 `queue_context`, 시장 `macro_ipo`(`config/analysis_sources.yaml`) — Pulse·Portfolio·Analysis·Valuation Queue가 같이 본다.
2. **적용 4곳**
   - 알파 점수: 정량 관심은 v1·v2가 이미 넣는다(이중 계산 금지). 판단 단계(Valuation Queue 2·Pulse 2b)는 '과밀'이거나 순위 상위인데 1차 사건이 없으면 gap을 올리지 않는다.
   - 내러티브: `radar/narrative_sources.py`가 evidence 파일에 `quantral`(집계·순위·Quantral 이야기 제목)을 넣는다. narrative-premium이 리테일 내러티브와 IB 내러티브의 차이를 쓴다.
   - 동인 notes: `queue_context.py --note` 한 줄 + 동인에 닿는 거시 지표 한 줄(숫자로 넣지 않는다).
   - Analysis 커뮤니티 반응: `social_view.stat_line`에 주간 리테일 순위·묶음 테마.
3. **저장 경계**: `social_surge.py --put`이 집계 뒤 받은 파일을 sourceType·detectedAt(+ 회사 점수·월간 게시 수)만 남게 덮어쓴다(`strip`). 남아 있던 원응답 파일도 같은 날 정리했다. 중복 제거용 해시(링크 해시, `radar/state` git 제외)는 링크가 아니라 남긴다.
4. **헤드리스**: 예약 실행(Pulse 11/13 23:55 회차가 Quantral로 받아 집계 갱신)과 `claude -p`(get_company_score AMAT 응답, 2026-11-14) 모두 호출됨을 확인.

## 근거
- 관심 급증 → 단기 초과수익 후 반전(Da, Engelberg & Gao 2011) — 그래서 관심은 블록 가중 IC 0.01·반감기 7일로 작게 넣고, 판단 단계에서 다시 더하지 않는다.
- 커뮤니티 신호는 S1·S2 — 주장(claim)이 아니다(CLAUDE.md). 수치는 집계만(ADR-011).

## 한계·반증
- Quantral 주간 순위: 첫 정규 실행(2026-11-15) 전 공백은 같은 날 W45(11/02~11/08)를 get_stories로 받아 메웠다(이야기 제목은 자기 말 요약·종류·게시 수·종목만, 채널 표본 없이 '채널 미확인'). 주중에는 직전 완결 주 순위다.
- social_surge 범위: 알파 5점 이상·Portfolio에 더해 Valuation Queue 대기열(우선 9.8)·최근 14일 Analysis 종목(9.7)을 넣었다(2026-11-14 마스터 "비어 있는 곳도 메워"). Pulse 회차당 15종목·6시간 재조회라 처음 채워지는 데 몇 회차가 걸린다. 미국 알파벳 티커만(Quantral 범위).
- 과밀 기준(Quantral 7일 점수 ≥ 70, Z < 1)은 맥락 표시용 사전값 — 알파 계산의 과밀 감점은 config/social_surge.yaml crowd_score를 따른다.
