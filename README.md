# 치입(Chiip) 사용 설명서

마스터 전용 반도체·AI 하드웨어 리서치 시스템입니다. 이 폴더 자체가 "자산"입니다. 기업·주장·테제·일정이 평문 파일로 쌓이고, 바뀐 기록은 git(변경 이력 관리 도구)과 GitHub(`SEOKD/chiip`, 비공개)에 남습니다.

**먼저 볼 것: [`docs/TODO_MASTER.md`](docs/TODO_MASTER.md)** — 로그인·키 입력 등 마스터가 직접 하셔야 시스템이 완전히 돌기 시작하는 일.

## 지금 상태 (2026-10-28, 1~6단계 구축 완료)
| 구성 | 상태 |
|---|---|
| 레이더(5분마다) | **가동** — 삼성전자·SK하이닉스·NVIDIA 뉴스룸, Google News(T0 한·영, T2), arXiv, 백악관. DART·네이버는 마스터 결정으로 제외(10-28) |
| 저빈도 수집(30분마다) | **가동** — 미국 관보(사전 공람 포함), SEC 전문 검색, 대만 월매출, 외국어 언론, 커뮤니티(HN), OpenAlex, 커널 메일링리스트, PCI ID, 미국 연방 지출, 오스틴 시의회 안건 |
| 모델 판정·알림 | **가동**(10-28 로그인·텔레그램 @chiip_dean_bot 연결) |
| 아침·저녁 브리프 | 데스크톱 앱 예약 작업 등록(07:00 / 평일 16:40) → claude.ai 비공개 페이지로 공유 |
| 가드레일 | 훅 6종 가동(주장 검증·투자/공개 출력 차단 규칙·엠바고·비밀키·금칙어·단위 경고) + 커밋 전 검사 |

## 무엇이 들어 있나
- **스킬 63종** (`.claude/skills/`) — 원천 등록·주장 등록·필드 인텔·실적 변화·레이더 판정·영향 카드·플래시·브리프·학회·IB 요약·지표·캐파·공급망·병목·논문·야마·역방향 레이더 13종·인재·조직 6종·미국 정부 7종·투자·공개 6종·분야 모듈 11종(draft)
- **서브에이전트 12종** (`.claude/agents/`) — radar-triage, impact-analyst, scout, triangulator, talent-analyst, policy-analyst, collector, tech-analyst, supply-analyst, fin-analyst, red-team, editor
- **수집 스크립트** (`radar/`) — 모델을 부르지 않는 결정론적 수집기. 판단만 모델

## 자주 쓰는 말 (치입에게 이렇게 말하면 됩니다)
| 하고 싶은 것 | 말하기 |
|---|---|
| 취재 메모 입력 | "필드 인텔 입력: …" (F4는 원문 대신 기업·주제·등급만) |
| 실적 분석 | "SK하이닉스 3분기 earnings-delta 해줘" |
| 기사 가치 판단 | "이거 야마 체크해줘" |
| 내 정리 검증 | "이 문장 reframe-check" |
| 논문 정리 | "이 논문 paper-digest" |
| 결론 공격 | "red-team 돌려줘" |
| 인사이트 게시 | "Notion 인사이트 초안 써줘" → 확인 후 "게시 승인" |

## 폴더 한눈에 보기
- `config/` 설정 · `radar/` 수집 · `sources/` 원문 · `knowledge/` 지식(자산) · `outputs/` 결과물 · `evals/` 품질 점검 · `scripts/` 검사·채점 · `docs/` 문서(`BUILD_PROMPT.md` §21이 최신 결정, `build_log.md` 진행 기록, `routines/` 예약 작업)

## 저장소 바깥 폴더 `D:\local-only\` — 절대 GitHub에 올라가지 않음
- `secrets\.env` — API 키를 **마스터가 직접** 입력합니다. 치입은 값을 보지 않습니다.
- `sealed\denylist.txt` — 취재원 이름 같은 금칙어를 한 줄에 하나씩. 저장·커밋 직전 자동 검사에만 쓰입니다.
- `sealed\field\`, `embargo\`, `licensed\` — 취재 메모·엠바고·유료 리포트 원문.

## 수동 명령 (터미널, 필요할 때만)
```
py radar/run_poll.py --force          # 레이더 즉시 1회
py radar/run_hourly.py --force        # 저빈도 수집 즉시 1회
py radar/notify.py "시험"              # 텔레그램 시험
py scripts/score_radar.py             # 레이더 성능
py -m unittest discover -s tests      # 자체 테스트
powershell -ExecutionPolicy Bypass -File scripts\install_scheduler.ps1   # 작업 스케줄러 재등록
```
작업 중지: `Unregister-ScheduledTask -TaskName "chiip-radar","chiip-hourly" -Confirm:$false`
