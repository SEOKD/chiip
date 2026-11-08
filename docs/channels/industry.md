# Chiip Industry Report — 운영 규칙

> 마스터 지시 2026-11-08 "Chiip Industry Report 기능도 만들자. BofA, Goldman Sachs, J.P Morgan, Morgan Stanley, Bernstein, UBS, Nomura, Mizuho, HSBC, Citi, TD Cowen, Wedbush, SemiAnalysis 등 리서치 하우스들의 산업 리포트 양식을 답습해 Chiip 자체적으로 분석 시스템을 갖춰라" → 초안·디벨롭 안 승인 단계.

## 마스터 결정(2026-11-08)
- **노션 위치:** 노션 최상위 `Industry` 페이지(https://app.notion.com/p/412b5d1e099880278f28ca96aaadf834) 아래에 산업별 하위 페이지를 만들고 리포트를 올린다. 이 페이지 아래만 쓴다.
- **산업 판단 등급:** 텐배거처럼 예외를 두고 제시한다. 등급은 규칙이 계산하고(사이클 국면 × 시장 기대 대비 차이 × 확신도), 모델 토론은 한 단계까지만 조정한다. 매매·비중·금액 지시는 쓰지 않는다. 등급은 산업 판단이고 개별 종목 투자 권유가 아니다(종목은 Analysis 리포트가 맡는다).
- **주기 — 세 축:** ① 주간 산업(매주 일요일 08:00 KST 산업 하나 — 2026-11-08 마스터 지시로 월간 트래커를 대체. 선정은 시니어 애널리스트식 시의성 점수 `config/industry_weekly.yaml`·`scripts/industry/weekly_pick.py`, 조립 `weekly_frame.py`, 절차 `docs/tasks/chiip-industry-weekly.md`, 예약 chiip-industry-weekly 05:30 작성·chiip-industry-weekly-send 08:00 발송) ② 분기 결산(실적 시즌 뒤 — 아직 조립 코드 없음) ③ 사건 때 심층(판단을 바꾸는 사건). 산업 입문서(Primer)는 산업마다 한 번 만들고 분기마다 고친다.

## 고정 원칙(설계안)
- 리서치 하우스의 형식·방법만 가져온다. 리포트 내용·도표·브랜드 상품명은 쓰지 않는다. IB 원문은 local-only에 두고 시장 기대의 증거로만 쓴다.
- 표지에 부가가치 원천(독점·해석·속도·정량)을 표시한다. 표시할 수 없으면 내지 않는다.
- 모든 숫자에는 claim id나 원자료가 있다. 데이터층(캐파·공급 관계·지표)이 비어 있으면 빈칸을 채우지 않고 '핵심 근거 부족'으로 끝낸다.
- 시범 산업부터 A~F 단계를 통과한 뒤 다음 산업으로 넓힌다.

## 사건 때 심층 — 논리 구조(2026-11-08 마스터 지시)
마스터의 논리를 고정 틀로 구현했다: ① 사건과 명목 해석(시장 반응 측정) ② 돈의 흐름(로비·PAC·슈퍼 PAC, 양당 확인 필수) ③ 지연 유인 vs 실행 압력 ④ 실행 경로와 시계(선거·취임 직후 창) ⑤ 산업 영향 ⑥ 시장 반영 vs Chiip(갭 → 산업 판단 등급) ⑦ 반대 검증 ⑧ 반증 조건·체크포인트(예측 장부).
절차는 스킬 `industry-event`, 설정 `config/industry_event.yaml`, 엔진 `scripts/industry/event_frame.py`, 렌더 `scripts/industry/industry_html.py`, 데이터 `knowledge/models/industries/events/<id>/`. 정당별 기업 PAC 기부는 `radar/usgov/fec_money.py`(FEC 공개 API, `.env` FEC_API_KEY 또는 DATA_GOV_API_KEY — 없으면 시간당 약 30회 DEMO_KEY).
첫 리포트: 2026-11-08 「블루 스윕은 데이터센터를 멈추지 않는다 — 값을 매긴다」(2026 중간선거 뒤 규제산업).
- **텔레그램 피드 양식**(2026-11-08 마스터 지시 "산업 리포트를 텔레그램 피드로 제공할 때 글이 가독성 있게 정리되도록"): `scripts/industry/tg_feed.py`가 리포트 JSON에서 조립한다 — 머리(종류·날짜) → 제목 → 산업 판단(등급별 묶음·🟢⚪🔴) → 핵심 Q&A 한 줄씩(괄호 풀이 빼고 절 경계에서 끊음) → 숫자 4개(기준 병기) → 다음 확인(날짜·무엇·Chiip 확률) → 링크 → 안내문. 문단 사이 빈 줄, 한 줄 120자 안. 손으로 쓰지 않는다.
