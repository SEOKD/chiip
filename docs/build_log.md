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
| 5~6 | 진행 예정 | |
