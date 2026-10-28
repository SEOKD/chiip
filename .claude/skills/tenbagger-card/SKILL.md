---
name: tenbagger-card
description: 텐배거(10배) 후보 발굴·카드·가상 추적(§21.14 3대 산출물 ③). 병목→해결 기술→작은 공급사 경로와 정량 요인 선별로 AI 하드웨어 밸류체인 중소형주를 찾고, 10배 경로 숫자·가격 내포 기대·킬 조건을 카드로 쓴 뒤 watch.csv에 등록일 가격과 함께 올린다. 예약 작업(주 1회) 또는 마스터 요청 시. 연구 후보이지 매수 권유 아님.
argument-hint: "[발굴 | 카드 <회사> | 점검]"
---

# tenbagger-card — 텐배거 후보 (ADR-010 §5, config/tenbagger.yaml)
## 발굴 (주 1회)
- 경로 A 병목(치입 엣지): 최근 `bottleneck-scan`·페어북·카드·학회에서 해소가 필요한 병목 → 해결 기술 → 그 기술의 **작은 공급사**(시가총액 구간 `universe.market_cap`). 양산 엔지니어 관점으로 "정말 그 회사 기술이 병목을 푸나"를 먼저 검증(금지표: 신기술 발표→경쟁우위, 샘플 출하→양산 성공).
- 경로 B 정량: `factors` 점수 상위(가격·재무 데이터 확보 후). 미국은 `knowledge/models/fundamentals/us/` 재무 이력으로 FCF 수익률·수익성 계산 가능.
- 주당 신규 후보 최대 2개. 억지로 채우지 않는다.

## 카드 (`knowledge/models/tenbagger/cards/TB-YYYYMMDD-NN.md`, 템플릿 `_template.md`)
- 10배 경로를 숫자로: TAM × 점유율 × 마진 → 5년 이익 → 출구 배수(등록부 id) → 내포 시가총액 / 현재. 10배에 필요한 가정과 그 확률(판단).
- 가격 내포 기대: 지금 주가가 이미 가정하는 성장(역DCF).
- 킬 조건 2~4개(측정 가능), 다음 카탈리스트, 반대 검증(`red-team`), 부가가치 원천.
- `prediction-log`에 측정 가능한 중간 예측 1개 이상 등록(owner 치입, origin 카드 id).

## 가상 추적 (`knowledge/models/tenbagger/watch.csv`)
- 등록 시 가격·날짜·시가총액(공개 시세, 출처 기록. 모르면 '미확인'으로 두고 다음 점검 때 채움). 행은 지우지 않는다.
- 월 1회 점검: 킬 조건 충족 → status 종료 + close_reason. 1·3·5년 성과를 기준지수 대비로 — 성적표이자 요인 가중치 피팅 재료(`model-lab`).

## 알파 점수 (마스터 지시 2026-10-28, `config/alpha.yaml`) — '텐배거 가능성' 10점
- 뜻: 실제 10배가 아니라 **그만큼 알파(초과수익)가 큰 종목**. 5.0 이상 종목만 어닝 캘린더 텔레그램에 실린다(`radar/markets/earnings_calendar.py`).
- 요소(0~10, 상방 한 방향): upside(상방 여지) · gap(가격 내포 기대가 낮음) · bottleneck(병목 노출, 치입 엣지) · asymmetry(작은 규모·낮은 커버리지·카탈리스트). 정의는 `config/alpha.yaml` components.
- 주 1회(토요일) **전 종목 재산정**: 대상 = `config/earnings_watch.yaml`의 valuation universe + extra + `master_stocks`(마스터 노션 Stocks) + `watch.csv` 추적 종목. 바뀐 종목만 `knowledge/models/alpha/judgments/YYYYMMDD.csv`에 쓴다(열 id,component,score,reason,evidence — 날짜 파일이 여러 개면 종목·요소별 최신 판단을 씀).
- 노션 Stocks에 새 종목 페이지가 생겼으면 `earnings_watch.yaml` extra·master_stocks에 추가하고 점수를 매긴다.
- reason 한 문장, evidence는 URL·카드 id·파일 경로. 근거가 약하면 4~6점과 '근거 약함'. 공개 자료만(local-only·필드 인텔·Informations 채널체크 금지).
- 끝나면 `py scripts/alpha/score.py --finalize`. 알파 점수는 매수 의견이 아니다.

## 경계
- invest 모드: local-only·필드 인텔 사용 금지, 목표주가·매수 의견 없음. 끝에 "공개 자료 기반 분석이며 투자 권유가 아님". 결정은 마스터.
- 텐배거는 기저율이 낮다 — 성과는 일화가 아니라 기저율 대비로 말한다.
