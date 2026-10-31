# 데이터 원천 운영 규칙

> CLAUDE.md '출력 채널'에서 옮긴 마스터 지시(2026-10-31, AAP-20261031-02). 새 지시도 여기에 적는다.

- **데이터 원천 = Fiscal.ai(MCP)**(2026-10-30 마스터 지시 "Pulse·Portfolio·Ten-bagger·Reporter·Analysis·Notion Tracker·Model Laboratory·Proviser·Weekly Review는 Easyconomics를 쓰지 말고 Fiscal.ai만 — 7가지 기능 모두", ADR-012): easyconomics MCP는 **퇴역**(호출 금지). 뉴스(종목·톱뉴스·중요도 1~5)·컨센서스(Zacks 평균·분산·5년 리비전·목표가·의견 + Fiscal 자체 추정·가이던스 출처)·재무/세그먼트/일별 배수/일봉·IR/트랜스크립트(Q&A·화자)/실적 일정·13F/내부자·펀드 레터·피어/Fiscal 포트폴리오(읽기 전용)를 `execute_code` 본보기 `scripts/fiscal/templates/*.js`로 받고 `scripts/fiscal/adapter.py`로 엔진 파일에 넣는다(데이터 계약 `knowledge/methods/data_fiscal.md`, 회사 키 `config/fiscal_keys.yaml`). **Zacks 수치를 보여 줄 때마다 'Data provided by Zacks Investment Research, Inc., www.zacksdata.com' 표기.** 일봉에 고가·저가가 없어 근사 표기, 공매도 거래량은 FINRA, 매크로는 FRED 공개 자료(Portfolio 시장 국면), 포지셔닝은 쓰지 않는다. fiscal.ai 링크는 응답의 auditUrl·terminalUrl만(손으로 만들지 않는다).
