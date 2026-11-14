# chiip-consumer-board — 소비 트렌드 보드 주간 갱신 (마스터 지시 2026-11-15 "주간 갱신 설정")

매주 일요일 09:00 KST(2026-11-15 마스터 지시로 토요일 09:30에서 변경). 대시보드 https://claude.ai/artifact/N2m2yXnCF1Us7owpj6Qcpk (비공개, Data 유형)의 고정 자료 파일 3개를 최신 수집분으로 바꾼다.
수집은 run_hourly가 이미 한다(radar/consumer_macro.py 6시간·radar/consumer_discovery.py 하루 1회). 이 작업은 보드를 다시 만들고 올리기만 한다 — 해석·텔레그램 발송 없음.

## 절차
1. 저장소 `C:\Users\석진\chiip`에서 `py scripts/consumer/trends_board.py` → `outputs/consumer/trends_<오늘>.md`.
2. `py scripts/consumer/board_export.py <스크래치 폴더>\ctrend_dash` → heat.json · series.json · discovery.json.
3. Artifact `action: "read"`로 위 대시보드를 먼저 읽는다(읽지 않은 대시보드에는 올리기가 거부된다).
4. 세 파일을 각각 Artifact `publish`(`url` = 위 대시보드, `asset: true`, `file_path` 한 개씩 — JSON은 한 번에 하나)로 올리고 새 `/_blob/…` 주소를 받는다.
5. ArtifactData로 `datasets/heat`·`datasets/series`·`datasets/discovery`를 `get`해 버전과 옛 blob 주소를 본 뒤, `batch` `update`(각 `if_version`)로 `source.url`만 새 주소로 바꾸고 `updated: {at: <UTC ISO 지금>, by: "Chiip chiip-consumer-board"}`, `edit: {via: "claude", at: <같은 시각>}`을 쓴다. `source`의 다른 칸·페이지(`files/index.html`)는 건드리지 않는다.
6. 옛 blob은 Artifact `delete`(`url` + `path` = 옛 id)로 지운다 — 방금 바꾼 세 개만, 이 작업이 올렸던 것만.
7. `data/users/me` 의 `check`를 읽는다. `failed`이거나 `runs`가 있으면 무엇이 틀렸는지 보고에 적는다(페이지 코드는 고치지 않는다 — 마스터에게 보고).
8. `outputs/consumer/trends_<오늘>.md`와 `knowledge/models/consumer_trends/` 변경분만 커밋·푸시(한국어 메시지, 다른 파일은 건드리지 않는다. --force·--no-verify 금지).
9. 보고: 문턱 업종 수·이름, 상향식 경보 수, 원천 오류(macro_latest.json·discovery_latest.json의 errors). 바뀐 것이 없으면 한 줄.

## 경계
- 수집기·설정·페이지를 고치지 않는다. 숫자를 지어내지 않는다 — 원천 오류면 그대로 보고.
- 공개 자료 기반 분석이며 투자 권유가 아님.
