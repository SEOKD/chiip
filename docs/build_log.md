# 구축 로그

> 대화가 길어져 요약되더라도 이어서 작업할 수 있도록 단계별 진행 상황을 남긴다.

## 마스터 지시 (2026-10-27 밤)
- 2~6단계 연속 진행, 게이트 생략. 권한 허용·폴더 생성 등 승인 절차는 모두 재가함.
- 단, 안전 규칙상 금지된 일(비밀번호·키 직접 입력, 계정 생성, 공개 게시 자동화)은 하지 않고 `docs/TODO_MASTER.md`에 남긴다.

## 공식 문서 확인 결과 (2026-10-27, code.claude.com)
- 스킬: `.claude/skills/<name>/SKILL.md`, 첫 줄 `---` 프론트매터(`name`, `description` 권장, `allowed-tools`, `model`, `context: fork`, `agent`, `disable-model-invocation`, `paths`). 본문 500줄 이내, 상세는 같은 폴더 보조 파일. `${CLAUDE_SKILL_DIR}`, `${CLAUDE_PROJECT_DIR}` 치환.
- 서브에이전트: `.claude/agents/<name>.md`, 필수 `name`·`description`, `tools`(허용 목록)·`disallowedTools`·`model`(`haiku|sonnet|opus|fable|inherit|전체 ID`)·`maxTurns`·`skills`(사전 로드)·`permissionMode`. 본문이 시스템 프롬프트.
- 훅: `.claude/settings.json`의 `hooks.PreToolUse[].matcher: "Write|Edit"` → `type: command`. stdin JSON에 `tool_name`, `tool_input.file_path`, Write는 `content`, Edit는 `new_string`. **exit 2 = 차단**(stderr가 Claude에 전달). Windows는 Git Bash가 있으면 셸 형식을 Git Bash로 실행.
- 헤드리스: `claude -p "<prompt>" --output-format json [--json-schema '<schema>'] --allowedTools "Read,Write" --permission-mode dontAsk|acceptEdits --permission-prompts none`. 구독 로그인은 `--bare`가 아닐 때 사용. `--bare`는 API 키 필요.

## 진행
| 단계 | 상태 | 비고 |
|---|---|---|
| 0 | 완료 | §21.8 |
| 1 | 완료 | 커밋 a4c1a80, 2770086 |
| 2 | 완료 | 커밋 8c3a8c8. field-intake 실전 시험은 마스터 메모 필요 |
| 3 | 완료 | 레이더 v0 가동(작업 스케줄러 chiip-radar 5분). DART·네이버·텔레그램 키, claude 로그인은 마스터 |
| 4 | 완료 | 훅 6종·에이전트 12종·분석 스킬·분야 모듈 11(draft)·역방향 v0(EDGAR·DART 타사·대만 월매출)·관보·작업 chiip-hourly |
| 5 | 완료 | claude.yml, 주간 리뷰·채점 6종, 역방향 v1 수집기 6종·스킬, 인재·미국 v1 스킬, Legistar 어댑터, 예약 작업(아침·저녁 등록 / 주간·역방향은 마스터 등록), CES 운용 문서 |
| 6 | 완료 | 투자·공개 스킬 6종(public-content는 Notion 게시 승인 필수), model_calc·propose_weights, v2 수집기(커널·PCI ID·USASpending), mirror-trade, 주가 원천 후보 문서, 오스틴 Legistar |

## 운영 시작 (2026-10-28)
- Claude CLI 로그인(Max) → 헤드리스 판정 실측 성공, 07:09 첫 자동 카드 3장
- 텔레그램 @chiip_dean_bot 연결, 07:17 시험 발송 성공. `notify.py --chat-id` 추가
- DART·네이버 수집 제외(마스터 결정, §21.6). 네이버 검색 API는 신규 신청 종료·개정 약관(AI 입력 금지)도 확인
- 아침 브리프 첫 실행이 도구 권한 대기로 멈춤 + 예약 작업 작업 폴더가 임시 폴더로 잡힌 문제 발견 → 세션을 저장소로 옮긴 뒤 4개 재등록(chiip-brief-morning·chiip-brief-evening·chiip-weekly-review·chiip-reverse-scout, 작업 폴더 `C:\Users\석진\chiip`, Auto 모드). 프롬프트에서 DART 제거, PATH 보정 안내 추가
- 앱이 Git·Python 설치 전 PATH로 떠 있어 훅이 모든 저장을 막음 → PC 재부팅으로 해결(훅은 수정하지 않음)
- 저녁 브리프에 '글로벌 공식 발표' 절 추가: PR Newswire 9개 피드 + Business Wire M&A 피드(`radar/pollers/press_wire.py`). MarketScreener(약관상 재사용 금지·자동 접속 403)·GlobeNewswire(자동 접속 403)는 제외
- 초안 1차 검토: `docs/reviews/2026-10-28_draft_review.md`
- 위클리 '글로벌 증시 주간 상승률'(Dean's Ticker 형식): Koyfin(API 없음·Plus 내보내기 없음)·TIKR(다운로드 불가) 검토 후 마스터가 EODHD 자동화 선택 → `radar/markets/weekly_movers.py`(토 06~09시, run_hourly 연결). 키 입력·일본 지원 확인·채널 게시 조건은 마스터 몫

## 마스터 할 일
`docs/TODO_MASTER.md`
