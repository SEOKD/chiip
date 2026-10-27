# 마스터가 직접 하실 일

> 치입이 안전 규칙상 대신할 수 없는 일(로그인·키 입력·계정 연결·공개 게시)과 마스터 판단이 필요한 일. 위에서부터 중요한 순서.

## A. 바로 하면 시스템이 '실제로' 돌기 시작하는 것

| # | 할 일 | 방법 | 효과 |
|---|---|---|---|
| 1 | **Claude CLI 로그인** (완료 10-28) | 터미널에서 `claude` 실행 → 안내에 따라 브라우저 로그인(한 번만) | 레이더 신규 항목을 모델이 자동 판정(P0 즉시 알림·P1 묶음). 지금은 판정 대상이 전부 브리프 대기열로 감 |
| 2 | **텔레그램 봇** (완료 10-28, @chiip_dean_bot) | 텔레그램에서 @BotFather → `/newbot` → 토큰 받기. 만든 봇에게 아무 말이나 보낸 뒤 채팅 id 확인 | 알림 수신. 지금은 `radar/state/outbox.log`에만 기록 |
| 3·4 | ~~DART·네이버 키~~ | **제외(2026-10-28 마스터 결정)** — 국내 공시·뉴스는 마스터가 이미 접함. `BUILD_PROMPT.md` §21.6 | 국내 레이더는 Google News(ko)·뉴스룸으로 최소 유지 |
| 5 | 키 입력 | `D:\local-only\secrets\.env` — `TELEGRAM_BOT_TOKEN=`, `TELEGRAM_CHAT_ID=` | 완료(10-28). 치입은 이 값을 보지 않습니다 |
| 6 | 알림 시험 | `py radar/notify.py "시험"` | 완료(10-28 07:17 발송 성공) |

선택 키: `SEC_USER_AGENT=이름 이메일`(SEC 접속 예절 — 없으면 일반 UA로 동작), api.data.gov 키(`REGULATIONS_GOV_API_KEY`, `CONGRESS_API_KEY`, `GOVINFO_API_KEY` — 의견서·의회 추적).

## B. Claude 데스크톱 앱에서

| # | 할 일 | 이유 |
|---|---|---|
| 7 | 사이드바 Scheduled → `치입 아침 브리프`, `치입 저녁 브리프` 각각 **Run now** 한 번 → 도구 권한 승인, 권한 모드 설정 | 이후 예약 실행이 권한 질문에서 멈추지 않음 |
| 8 | **New task**로 2개 등록: `docs/routines/weekly-review.prompt.md`(토 09:00, `0 9 * * 6`), `docs/routines/reverse-scout.prompt.md`(매일 08:30, `30 8 * * *`) | 자동 등록이 권한 검사에서 거부됨 — 우회하지 않고 남겨 둠 |
| 9 | **Notion 커넥터 연결**(연결 카드 또는 Settings → Connectors) | 인사이트 게시용. 게시는 매번 마스터 승인 후 |

## C. GitHub

| # | 할 일 | 방법 |
|---|---|---|
| 10 | @claude 연동 | 터미널 `claude` → `/install-github-app` (또는 `claude setup-token` → 저장소 Settings → Secrets에 `CLAUDE_CODE_OAUTH_TOKEN`) + Claude GitHub App 설치 |
| 11 | 브랜치 보호(선택) | 결정 ②로 마스터 본인 커밋의 main 직접 반영을 허용했으므로, 보호 규칙을 켜려면 "관리자 우회 허용"으로 |

## D. 검토·결정 (치입이 초안을 만들어 둔 것)

| # | 대상 | 파일 |
|---|---|---|
| 12 | 행동 규칙 | `CLAUDE.md` |
| 13 | 감시 기업 T1 후보 10·T2 후보 15 확정 | `config/watchlist.csv` |
| 14 | 키워드·알림 규칙·폴링 간격 | `config/keywords.yaml`, `config/alert_rules.yaml` |
| 15 | 다국어 사전 7종(draft) | `config/lexicon/` |
| 16 | 페어 가설 5개 우선순위 | `knowledge/pairs/` |
| 17 | 거울 매트릭스 대만 코드(6274는 장외라 미수집) | `config/mirror_matrix.yaml` |
| 18 | 분야 모듈 11종 기술 내용 — 특히 포토·트랙·EUV·메모리 공정 | `.claude/skills/domain-*` |
| 19 | 커뮤니티 원천: Reddit 켤지, 구독할 Substack 피드 | `config/community_sources.yaml` |
| 20 | 웹 변경 감시 페이지, 잡보드 대상 | `config/page_watch.yaml`, `config/job_boards.yaml` |
| 21 | 주가·컨센서스 원천 선택 | `docs/market_data_options.md` |
| 22 | 미국 거점 회의 플랫폼(테일러·윌리엄슨 카운티·웨스트라피엣·티피카누 카운티) — 오스틴은 Legistar 확인됨 | `config/us_gov/sites.yaml` |

## E. 실전 시험 (게이트 대신)

| # | 할 일 |
|---|---|
| 23 | 방법론 문서 2개를 `docs/methodology/`에 넣기 → 규칙 후보·충돌 목록 작성 요청 |
| 24 | 취재 메모 3건으로 `field-intake` 시험(F4는 원문 대신 포인터만) |
| 25 | SK하이닉스 3분기 실적(2026-10-28 오전)으로 `earnings-delta` 실전 시험 — 2분기 주장 C-20261027-001~005가 비교 기준 |
| 26 | CES 이후: 역방향 백테스트 사건 10건 선정(`reverse-backtest`) |
