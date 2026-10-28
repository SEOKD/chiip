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
| 7 | ~~브리프 권한 모드~~ | **완료(10-28)** — 예약 작업 4개(아침·저녁 브리프, 주간 리뷰, 역방향 판정)를 저장소 폴더·Auto 모드로 재등록. 바꾸려면 Scheduled에서 작업 편집 |
| 8 | ~~주간·역방향 등록~~ | **완료(10-28)** — chiip-weekly-review(토 09:00), chiip-reverse-scout(매일 08:30) |
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
| 21 | ~~EODHD 무료·$29.99 요금제~~ → 21-0 ALL-IN-ONE으로 통합(위클리 주간 상승률·가격 포함). 같은 `EODHD_API_KEY` 하나로 쓴다 | `radar/markets/weekly_movers.py` |
| 21-0 | **✅ 결정: EODHD ALL-IN-ONE 승인(10-28).** 마스터 할 일: ① eodhd.com 가입 → ALL-IN-ONE 구독(월 $99.99 또는 연 $999.90 ≈ 월 $83.33, 2026-10-28 요금표) ② 대시보드의 API 토큰을 `D:\local-only\secrets\.env`에 `EODHD_API_KEY=` 한 줄로 입력(채팅에 붙여 넣지 않기) ③ 치입에게 '키 넣었다' → 치입이 키 존재만 확인하고 종목 코드 일괄 확인(한국 KO·KQ·대만·일본 지원 여부는 요금표에 명시 없음 — 키로 직접 확인), 가격 30년+·펀더멘털 이력 백필, B단계(피팅·DCF 실수치·텐배거 정량 선별) 착수. 개인 요금제 데이터는 표시·재배포 금지 — 결과는 비공개(저장소·비공개 Artifact)로만. 한국 추정치가 비면 T0 7종목만 `manual_consensus.csv` 주 1회 | `config/valuation.yaml`, `knowledge/models/valuation/README.md` |
| 21-1 | Business Wire 피드 주소 추가: 브라우저에서 businesswire.com RSS 페이지 → Semiconductor·Technology·Earnings·Contracts 피드 주소 복사 → 치입에게 전달 | `config/press_wire.yaml` (지금은 M&A 피드만) |
| 21-2 | 예약 작업 산출물(브리프·역방향 요약)은 커밋하지 않고 남음 — 마스터 세션에서 "브리프 커밋해"로 일괄 커밋 | `outputs/brief/`, `radar/cards/` |
| 21-3 | **X 공식 API 비용 승인 여부(10-28).** 리서치·투자자 X 계정 감시는 코드 완성·꺼짐 상태. 사용량 과금(글 1건 $0.005, 29개 계정 예상 월 4~5천 건 ≈ $20~25, 월 상한 1만 건 ≈ $50 안전장치). 승인 시: ① console.x.com 개발자 계정·크레딧 구매(마스터 직접) ② Bearer Token을 `D:\local-only\secrets\.env`에 `X_BEARER_TOKEN=`으로 입력 ③ 치입에게 'X 켜' → 등록부 enabled·§21.6·CLAUDE.md 제외 원천 문구 수정. 계정 목록에서 `x_handle: null`·`# verify` 항목 확인·추가 | `config/research_watch.yaml`, `config/source_registry.yaml` src-research-x |
| 21-4 | **노션·SEC 키(10-28).** ① 노션 ⭐ 즉시 기록을 원하면 notion.so/profile/integrations에서 내부 통합 생성 → 허브 '치입 인텔리전스' 페이지 ⋯ → 연결 추가 → 토큰을 `.env`에 `NOTION_TOKEN=` (없으면 매일 06:40에 반영) ② SEC 접속 규칙상 연락처가 든 User-Agent를 `.env`에 `SEC_USER_AGENT="Chiip research <연락 이메일>"` ③ 포커스 점수 기준·가중치·고정 종목(always_include) 검토 | `config/focus.yaml`, `config/notion.yaml` |
| 21-5 | **부가가치 엔진(10-28, §21.14·ADR-010).** ① 노션 '오피니언·인사이트'에 글을 쓰고 `상태`를 작성 중·완성으로 두거나 `검토 요청`을 체크하면 매일 07:30·21:30에 치입이 검토(하위 페이지 '치입 검토' + 판정·정성 점수·정량 갭) ② 텐배거 유니버스 추천안 검토 — 시가총액 구간(한국 1,000억~2조 원, 미·대만·일 1억~30억 달러)·요인 사전값 ③ **B단계(피팅·DCF 실수치·텐배거 정량 선별)는 21-0 데이터 요금제 결정이 선행 조건** ④ 기사 소재 채택 시 치입에게 '○○ 채택'이라고 말해 주면 성적표에 반영 | `config/tenbagger.yaml`, `knowledge/models/params/registry.yaml` |
| 22 | 미국 거점 회의 플랫폼(테일러·윌리엄슨 카운티·웨스트라피엣·티피카누 카운티) — 오스틴은 Legistar 확인됨 | `config/us_gov/sites.yaml` |

## E. 실전 시험 (게이트 대신)

| # | 할 일 |
|---|---|
| 23 | 방법론 문서 2개를 `docs/methodology/`에 넣기 → 규칙 후보·충돌 목록 작성 요청 |
| 24 | 취재 메모 3건으로 `field-intake` 시험(F4는 원문 대신 포인터만) |
| 25 | SK하이닉스 3분기 실적(2026-10-28 오전)으로 `earnings-delta` 실전 시험 — 2분기 주장 C-20261027-001~005가 비교 기준 |
| 26 | CES 이후: 역방향 백테스트 사건 10건 선정(`reverse-backtest`) |
