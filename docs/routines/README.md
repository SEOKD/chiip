# 루틴·예약 작업 (BUILD_PROMPT §15.5, §4.3)

## 지금 돌고 있는 것
| 이름 | 어디서 | 주기 | 하는 일 | 상태 |
|---|---|---|---|---|
| chiip-radar | Windows 작업 스케줄러 | 5분 | radar/run_poll.py — 국내 T0 공시·뉴스·뉴스룸, T2·arXiv·백악관 RSS 수집 → 규칙 P0 선알림 → 새 항목 판정(run_triage) | 가동 |
| chiip-hourly | Windows 작업 스케줄러 | 30분 | radar/run_hourly.py — 관보(정식·사전 공람), EDGAR 전문 검색, DART 타사·공시유보, 대만 월매출, 커뮤니티, 외국어 언론, OpenAlex, 웹 변경, 잡보드, Legistar | 가동 |
| chiip-morning-brief | Claude 데스크톱 앱 예약 작업 | 매일 07:00 | 아침 브리프 → outputs/brief + claude.ai 비공개 Artifact | 등록됨 |
| chiip-evening-wrap | Claude 데스크톱 앱 예약 작업 | 평일 16:40 | 저녁 브리프 → outputs/brief + Artifact | 등록됨 |
| chiip-weekly-review | Claude 데스크톱 앱 예약 작업 | 토 09:00 | 주간 리뷰 | **마스터 등록 필요** — 아래 프롬프트 |
| chiip-reverse-scout | Claude 데스크톱 앱 예약 작업 | 매일 08:30 | 역방향 후보 판정·삼각측량 | **마스터 등록 필요** — 아래 프롬프트 |

데스크톱 앱 예약 작업은 앱이 켜져 있을 때 실행된다(꺼져 있으면 다음 실행 때 실행).
처음 한 번은 앱의 Scheduled 화면에서 각 작업의 "Run now"를 눌러 도구 권한을 승인해 두면 이후 멈추지 않는다.

## 마스터가 직접 등록할 예약 작업 (자동 등록이 권한 검사에서 거부됨)
앱 사이드바 Scheduled → New task 에서 아래 프롬프트를 붙여 넣는다.
- `weekly-review.prompt.md` — 토 09:00 (cron `0 9 * * 6`)
- `reverse-scout.prompt.md` — 매일 08:30 (cron `30 8 * * *`)

## 클라우드 루틴 (PC가 꺼졌을 때 폴백, 선택)
GitHub에 Claude 앱 연결(`/install-github-app`) 후 Claude Code의 `/schedule`로 만든다. 프롬프트: `cloud-fallback.prompt.md`.
클라우드는 `D:\local-only`에 접근할 수 없으므로 필드 인텔 대조는 하지 않는다. 결과는 `claude/` 브랜치 PR.