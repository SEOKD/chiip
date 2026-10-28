---
name: weekly-review
description: 주간 리뷰(토요일 오전): 글로벌 증시 주간 상승률(Dean's Ticker 형식), 테제별 변화, 지표 변화, 예측 진행, 다음 주 카탈리스트, 레이더·역방향·필드 인텔 성능. outputs/brief/에 저장하고 claude.ai 비공개 Artifact로 공유.
argument-hint: "[주차 YYYY-Www]"
---

# weekly-review — 주간 리뷰 (§7.2)
## 입력
- 지난 7일 카드·주장(novelty 신규·수정), 테제 파일 판단 변경 이력
- `py scripts/score_radar.py`, `score_reverse.py`, `score_field_intel.py`, `score_predictions.py` 결과
- `knowledge/models/indicators.csv`, `mirror_monthly.csv` 변화
- 다음 주 `knowledge/calendar.csv`
- **주간 상승률 데이터**: `knowledge/models/weekly_movers/YYYY-Www.csv` (`radar/markets/weekly_movers.py`가 토요일 06~09시에 EODHD 스크리너로 만든 결정론적 데이터. 열: region, rank, pct_change, name_en, ticker, exchange, currency, market_cap_usd, sector, industry, last_day, as_of). 등락률은 최근 5거래일 기준 — 휴장일이 낀 주는 그 사실을 한 줄 적는다. `radar/state/weekly_movers.json`의 `missing`에 있는 지역은 "데이터 미수집"

## 글로벌 증시 주간 상승률 절 — 마스터 채널 'Dean's Ticker'(https://t.me/d_ticker, 마스터 소유) 형식
```
NN주차 글로벌 증시 주간 상승률

US (https://t.me/d_ticker)
+23%｜지스케일러｜사이버보안
…(20개)

US(<$10B) (https://t.me/d_ticker)
…(10개)

Europe (https://t.me/d_ticker)
…(10개)

Japan (https://t.me/d_ticker)
…(10개)

Korea (https://t.me/d_ticker)
…(10개)
```
- 줄 형식: `+NN%｜한글 회사명｜한글 업종 짧게`. 구분자는 전각 세로선 `｜`. 등락률은 반올림 정수, `+` 부호.
- 개수: US 20, US(<$10B) 10, Europe·Japan·Korea 각 10. 시가총액 기준선은 수집기 설정(`config/weekly_movers.yaml`)을 따른다.
- 회사명은 한국에서 통용되는 한글 표기(예: Zscaler → 지스케일러, Check Point → 체크포인트). 업종은 '사이버보안', '고객관리 SW', '위탁임상(CRO)'처럼 2~10자로 사업 핵심을 쓴다. 확신 없는 표기는 영문 그대로 둔다.
- **숫자는 데이터 파일 값만 쓴다.** 파일이 없거나 지역이 비면 그 지역에 "데이터 미수집 — 미확인"이라고 쓴다. 웹 검색으로 등락률을 채우지 않는다(종목 수십 개의 주간 수치를 검색으로 맞추는 것은 오류가 크다).
- 이 절 아래에 반도체·AI 하드웨어·소프트웨어 종목만 골라 "치입 관점 한 줄"(왜 올랐나 — 원인 사건을 특정할 수 있을 때만, 못 하면 '원인 미확인')을 붙인다. "주가 급등 → 펀더멘털 변화" 연결 금지.
- 채널 게시는 마스터가 직접 한다(P15). 위 블록은 그대로 복사해 붙일 수 있게 코드 블록으로도 한 번 더 둔다.

## 형식
```
[모드: brief / 범위: YYYY-Www / 기준시각: …]
■ 이번 주 한 문장
■ 글로벌 증시 주간 상승률 (Dean's Ticker 형식) + 반도체·AI 종목 한 줄
■ 섹터 밸류에이션 (`py scripts/valuation/engine.py --digest evening` + 하위 섹터별 NTM P/E 중앙값·리비전·반영도 주간 변화, 내러티브 단계 변화)
■ 테제별 변화 (강화·약화·무관, 근거 id)
■ 지표·거울 데이터
■ 예측 원장 (만기 도래·판정)
■ 다음 주 카탈리스트 (event-preview 필요 목록)
■ 시스템 성능 (탐지 지연·누락·장애·경보 정밀도)
■ 개선 제안 (원천·키워드·규칙 — 마스터 승인 대상)
```
## 저장·공유
`outputs/brief/YYYY-Www_weekly.md` + claude.ai 비공개 Artifact(로컬 전용 정보 제외, 필드 인텔은 source_class 집계만).
