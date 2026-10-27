# 치입(Chiip) 사용 설명서

마스터 전용 반도체·AI 하드웨어 리서치 시스템입니다. 이 폴더 자체가 "자산"입니다. 기업·주장·테제·일정이 평문 파일로 쌓이고, 바뀐 기록은 git(변경 이력 관리 도구)에 남습니다.

## 지금 상태 (1단계 — 뼈대)
- 폴더 구조, 규칙 파일(`CLAUDE.md`), 감시 목록, 키워드, 일정, 검증 스크립트가 준비된 상태입니다.
- 아직 자동 수집(레이더)은 돌지 않습니다. 3단계에서 붙입니다.

## 먼저 읽을 파일
| 파일 | 무엇인가 | 마스터가 할 일 |
|---|---|---|
| `CLAUDE.md` | 치입이 매번 읽는 행동 규칙 | 읽고 고칠 곳 표시 |
| `config/watchlist.csv` | 감시 기업 목록 (T0 확정, T1·T2 후보) | 후보 중 넣을 곳·뺄 곳 결정 |
| `config/keywords.yaml` | 분야별 감시 키워드 | 빠진 키워드 추가 |
| `knowledge/calendar.csv` | 앞으로의 학회·실적 일정 | 확인 |
| `docs/BUILD_PROMPT.md` | 전체 구축 지시서 (§21이 최신 결정) | 필요할 때 |

## 폴더 한눈에 보기
- `config/` 설정 · `radar/` 자동 수집 · `sources/` 원문 · `knowledge/` 지식(자산) · `outputs/` 결과물 · `evals/` 품질 점검 · `scripts/` 검사 도구 · `docs/` 문서

## 저장소 바깥 폴더 `D:\local-only\` — 절대 GitHub에 올라가지 않음
- `secrets\.env` — API 키를 **마스터가 직접** 입력합니다. 치입은 값을 보지 않습니다.
- `sealed\denylist.txt` — 취재원 이름 같은 금칙어를 한 줄에 하나씩 적습니다. 커밋 직전 자동 검사에만 쓰입니다.
- `sealed\field\`, `embargo\`, `licensed\` — 취재 메모·엠바고·유료 리포트 원문.
- F4(봉인) 메모는 치입에게 원문으로 주지 않습니다. 요지 태그와 등급만 알려 주세요.

## 필요한 프로그램 (설치 전)
| 프로그램 | 왜 필요한가 | 설치 명령 (PowerShell, 승인 후) |
|---|---|---|
| Git | 변경 이력 기록·GitHub 연결 | `winget install --id Git.Git -e` |
| Python 3.12 | 검사·수집 스크립트 실행 | `winget install --id Python.Python.3.12 -e` |
| pyyaml | YAML 파일 읽기 | `py -m pip install -r requirements.txt` |

## 검사 스크립트 (Python 설치 후)
```
py scripts/validate_claims.py      # 주장 파일 필수 항목 검사
py scripts/check_units.py outputs  # 단위 표기 경고
py scripts/scan_sealed.py          # 금칙어·비밀키 유출 검사 (커밋 때 자동 실행)
```

## GitHub 연결 (나중에, 안내에 따라)
1. github.com에서 **비공개(Private)** 저장소 `chiip`을 만듭니다(README 추가 체크 해제).
2. 치입에게 "GitHub 연결해 줘"라고 하면 주소 연결 명령을 안내합니다.
