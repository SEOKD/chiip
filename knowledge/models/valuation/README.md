# 밸류에이션 데이터 (docs/valuation/framework.md)

| 파일 | 만드는 쪽 | 내용 |
|---|---|---|
| `snapshots/YYYYMMDD.csv` | `radar/markets/valuation_data.py` (코드) | 그날의 가격·추정치·리비전·멀티플 원자료 — **리비전 이력이라 보존·커밋** |
| `prices/<code>.csv` | 같은 수집기 | 가격 이력(다시 받을 수 있어 git 제외) |
| `history/YYYYMMDD.csv` | `scripts/valuation/engine.py` (코드) | 그날의 계산 결과(자기 역사 백분위의 기준) |
| `latest.csv` · `latest.json` | 엔진 | 최신 계산(git 제외) |
| `scenarios.csv` | 스킬 `valuation-card` (모델) | 약세·기본·강세 시나리오 — 근거 id 필수, 수정 대신 새 as_of 행 추가 |
| `manual_consensus.csv` | 마스터 수동 입력 | EODHD에 없는 종목(한국 등)의 컨센서스. period: `0y`(올해)·`+1y`(내년), source에 출처(예: 화면 이름·날짜) |

- EODHD 개인 요금제 데이터는 표시·재배포 금지 — 이 폴더 내용과 계산 결과는 비공개(저장소·비공개 Artifact)로만 쓴다.
