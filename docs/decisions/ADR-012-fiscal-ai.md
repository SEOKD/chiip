# ADR-012 데이터 원천을 easyconomics에서 Fiscal.ai(MCP)로 바꾼다

- 날짜: 2026-10-30 · 결정: 마스터 지시 · 상태: 채택
- 지시: "Chiip Pulse, Chiip Portfolio, Chiip Ten-bagger, Chiip Reporter, Chiip Analysis, Chiip Notion Tracker, Chiip Model Laboratory, Chiip Proviser, Chiip Weekly Review는 이제 앞으로 Easyconomics를 쓰지 말고 Fiscal.ai만 MCP로 연결해 써라. 7가지 기능(뉴스·컨센서스/추정치·재무/세그먼트·IR/어닝콜·수급/지분·펀드 레터·기타)을 모두 쓰도록 하라. 지금부터 시스템 엔진 아키텍처에 이를 전부 반영하라."

## 결정
1. 9개 예약 기능의 기업·시장 데이터는 Fiscal.ai MCP(`api_docs`·`execute_code`)만 쓴다. easyconomics MCP는 퇴역 — 호출 금지(과거 산출물·데이터 묶음의 'easyconomics' 출처 표기는 그날의 사실로 남긴다).
2. 호출은 샌드박스 자바스크립트(60초·동시 6개)라 **샌드박스 안에서 줄이고 계산**한다: 본보기 `scripts/fiscal/templates/*.js`(fundamentals·prices·news·consensus·holders·fund_letters·transcript_qa) → 출력 파일 → `scripts/fiscal/adapter.py`(fundamentals.json·ohlcv.csv·ohlcv_m.csv·회사 키 캐시 `config/fiscal_keys.yaml`). 판단은 모델, 파일 반영은 결정론 — 기존 원칙과 같다.
3. 7개 기능의 엔진 배치는 `knowledge/methods/data_fiscal.md` 표가 정본이다(기능별·단계별).

## 근거
- 같은 연결로 뉴스 중요도 분류, Zacks 컨센서스의 분산·5년 리비전 이력(리비전 신호의 피팅 자료), 공시 원문 페이지 링크(auditUrl), 화자·Q&A 구간이 붙은 트랜스크립트(애널리스트 질문 추출), 13F·내부자, 펀드 레터 논지(바이사이드 층)를 함께 받는다 — easyconomics에 없던 바이사이드·리비전 이력이 생긴다.
- 일봉 전체 이력(수십 년)을 샌드박스에서 월봉으로 줄여 받을 수 있어 장기 월봉 피보나치가 가능해졌다(easyconomics는 5년 응답이 가운데가 잘렸다).

## 대가·제약
- **Zacks 표기 의무**: Zacks 수치(컨센서스·목표가·의견·Street 선행 배수)를 보여 줄 때마다 "Data provided by Zacks Investment Research, Inc., www.zacksdata.com"(https://www.zacksdata.com). Fiscal.ai 자체 추정·가이던스·재무는 해당 없음.
- Zacks는 미국 상장·달러 기준 — 한국·일본 원주는 비어 있을 수 있다(그때 '미확인', 노션 Stocks 마스터 입력·회사 자료).
- 일봉에 고가·저가가 없다 → 캔들·CLV는 시가·종가 근사(리포트에 자동 표기). 공매도 거래량·매크로·포지셔닝은 Fiscal.ai에 없다 → 공매도는 FINRA, 매크로·포지셔닝은 쓰지 않는다.
- 결정론 스크립트는 MCP를 직접 부를 수 없다(키가 필요한 REST API) — 마스터가 Fiscal.ai API 키를 주면 수집기가 직접 받게 바꿀 수 있다(TODO_MASTER, 선택).

## 반대 근거
- 한 원천 집중 위험(장애·한도). → 1차 서류(SEC·회사 IR·FINRA)는 계속 병행하고, 숫자는 auditUrl로 원문 대조한다(datapack_check·Proviser 리포트 점검).
