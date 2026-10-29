---
name: notion-intake
description: 마스터가 노션 Insights·Informations·Stocks에 새로 올리거나 고친 페이지를 역할별로 즉시 분석해 결과물을 만들고 텔레그램으로 보낸다(마스터 지시 2026-10-28 "올리는 즉시 파악해 실시간으로 결과물을 만들고 텔레그램으로 — 일일이 입력하면 챗봇이지 에이전트가 아니다"). radar/notion_watch.py(헤드리스)·예약 작업 chiip-notion-watch가 부른다.
argument-hint: "<insights|informations|stocks> <page_id> [inbox 텍스트 경로]"
---

# notion-intake — 노션 올림 즉시 처리
입력: 역할, 노션 페이지 id, (있으면) `radar/notion/inbox/<id>.md` — 감시기가 뽑은 본문·첨부(xlsx 표) 텍스트. 없으면 노션 커넥터로 fetch(첨부는 notion-get-file-download-urls로 받아 표준 라이브러리로 읽기).
마스터는 요청을 따로 쓰지 않는다 — **페이지에 담긴 의도를 읽고 마스터가 다음에 물을 질문에 먼저 답한다.** 마스터 가설이 적혀 있으면 같은 강도로 반대 검증한다.

## 공통 산출물 (모든 역할)
1. 상세: `outputs/report/notion/<YYYYMMDD>_<id 앞 8자>.md` — 첫 줄 모드 표시, 공통 구조(결론 → 인과 사슬 → 근거 표 → 반대 검증 → 반증 조건·다음 확인 → 종료 상태), 부가가치 원천.
2. 텔레그램 문안: `outputs/report/notion/<YYYYMMDD>_<id 앞 8자>_tg.txt` — 15줄 이내. 첫 줄 `[노션 <역할>] <제목> — <한 줄 결론> (1차 판정, 미검증)`, 핵심 3~5줄, 반대 근거 1줄, 다음 확인 1줄, 상세 경로, invest성 내용이면 끝에 `공개 자료 기반 분석이며 투자 권유가 아님`.
   - 헤드리스(감시기)에서는 문안만 쓰면 감시기가 보낸다. 예약 작업에서는 `py -c "import sys; sys.path.insert(0,'radar'); import notify; notify.send(open('<tg 경로>',encoding='utf-8').read(), 'NOTION')"`로 직접 보낸다.
3. 처리 표시: 예약 작업에서는 `py scripts/notion_state.py mark <page_id> <수정시각 또는 -> <상세 경로>` (헤드리스는 감시기가 표시).

## 역할별
### Informations (수집 정보 = 근거 재료) — 가장 흔한 경우
- 정보 유형 판정: 정책·법안 / IB 리포트 요지 / 채널체크 / CAPEX·산업 데이터 / 학회·기술 / 기타.
- **정책·법안**: `policy-flash` 원리 — 단계(발의·위원회·본회의·서명·시행, 규칙안·최종·시행)를 1차 출처(congress.gov·연방관보·감독기관 공지)로 확인, 일정(선거·회기·시행일), 누가 수혜·피해(경로·민감도 상·중·하·주가 위치), 마스터 가설 반대 검증, 다음 확인 사건.
- **IB 리포트 요지**: 라이선스 자료 취급 — 숫자·문장을 상세 파일·텔레그램에 옮기지 않고 자기 말 요지만, `ib-digest` 원리(의견·추정치 변경·새 데이터·치입 판단과 차이). 치입 claim·포커스·알파 점수와 어긋나는 곳을 짚는다.
- **채널체크**: 필드 인텔일 수 있다 → 텔레그램에는 '채널체크 반영: 영향 종목 n개, 상세 로컬'만. 대조는 로컬 상세 파일에만, invest성 판정 근거로 쓰지 않는다. 취재원 단서가 보이면 즉시 멈추고 '필드 인텔 등급 확인 필요'만 알린다.
- **CAPEX·산업 데이터**: `indicator-update`·`valuation-bridge` 원리 — 숫자가 어느 종목의 실적 동인(물량·ASP·점유율)에 닿는지, 컨센서스와 차이.
- 영향 종목은 알파 점수(`knowledge/models/alpha/latest.json`)·포커스 점수와 함께 적고, 5.0 경계를 넘을 만한 종목은 `knowledge/models/alpha/judgments/<오늘>.csv`에 판단을 추가한 뒤 `py scripts/alpha/score.py --finalize`.

### Insights (마스터 인사이트 글)
- 스킬 `insight-review` 절차 전체. 노션 기록은 글 아래 하위 페이지 '치입 검토 YYYY-MM-DD'만 — 헤드리스에서는 `py scripts/notion_write.py child <page_id> "치입 검토 YYYY-MM-DD" <상세 파일>`, 예약 작업에서는 노션 커넥터. `py scripts/insight_state.py mark …`도 함께.

### Stocks (종목·테마 커버리지)
- 종목 페이지(제목 '회사명 티커'): `config/earnings_watch.yaml` extra·master_stocks에 없으면 추가(id·name·code·region·sub, code 미검증 표시) → 알파 판단 4요소를 써서 finalize → 페이지에 마스터 메모가 있으면 그 논지를 짧게 검토(가장 약한 고리·다음 확인). 다가오는 실적 일정이 있으면 함께 적는다.
- 테마 페이지(OCP 2026·해양시추 등): 관련 종목 목록·내러티브 단계(`narrative-premium` 원리)·치입 감시 목록과의 겹침.
- **텐배거 리포트 우선 색인**(마스터 지시 2026-10-30 "Stocks 티커 중 최신(±7일) 어닝콜 스크립트와 컨센서스를 입력해 놓은 종목부터 분석"): 종목 페이지를 새로 보거나 고친 것을 볼 때마다 본문을 `radar/inbox/notion_stocks/<page_id>.md`(git 제외)에 저장하고 `py scripts/tenbagger/notion_stocks.py --classify radar/inbox/notion_stocks/<page_id>.md --page-id <id> --title "<제목>" --edited <편집일>` — 어닝콜 스크립트·컨센서스·IB 내용·콜 날짜를 규칙으로 판별해 색인(knowledge/models/notion/stocks_index.json)에 넣는다. 판별은 스크립트가 한다(모델은 읽기만).

## 경계
- local-only 읽기 금지. 마스터 노션 페이지(Insights·Informations·Stocks)는 **읽기만** — 수정·삭제 금지(Insights 하위 '치입 검토' 페이지 생성만 허용).
- 목표주가·매수/매도 표현 금지. 잘못된 연결 금지표 적용(법안 발의 → 시행, 주가 급락 → 원인 특정).
- 원문 전체 복제 금지(메타 + 자기 말 요약 + 링크). 첨부 원본은 저장소에 넣지 않는다.
