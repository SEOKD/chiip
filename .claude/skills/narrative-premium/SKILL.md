---
name: narrative-premium
description: 알파 레이더로 텐배거(알파) 후보를 평가할 때, 그 기업과 섹터의 멀티플 프리미엄(또는 디스카운트)을 결정하는 내러티브 요인을 미국 투자 커뮤니티(Substack·Seeking Alpha·Motley Fool·Benzinga·MarketBeat·Barron's·IBD 등, 약관 준수 원천)와 IB 커버리지 변화·애널리스트 질문으로 파악한다(마스터 지시 2026-10-28). 알파 5점 이상 동인 작성 전, 또는 마스터 요청 시.
argument-hint: "<entity_id> [<entity_id> ...]"
---

운영 규칙: `docs/channels/tenbagger.md`를 먼저 읽는다.

# narrative-premium — 멀티플 프리미엄의 내러티브 (Damodaran '이야기 → 숫자', Shiller 내러티브 경제학)
목적: "왜 시장은 이 회사(섹터)에 이 멀티플을 주는가 / 무엇이 바뀌면 멀티플이 바뀌나"를 근거와 함께 적는다. 커뮤니티·IB 의견은 **사실이 아니라 시장 기대의 증거**다.

## 1. 근거 모으기 (결정론)
- `py radar/narrative_sources.py <id>` → `knowledge/narratives/evidence/<id>.json`: 커뮤니티 헤드라인(Google News 색인 제목), IB 커버리지 변화(개시·상향·하향·목표가 제목), 섹터 헤드라인, Substack 10곳 언급, Hacker News.
- 모델 단계(가능하면, Fiscal.ai — knowledge/methods/data_fiscal.md): `consensus.js`(Zacks 목표가·의견 분포·5년 리비전 — 표기 의무), `transcript_qa.js`(셀사이드가 콜에서 묻는 것 = IB 내러티브의 초점), `fund_letters.js`(바이사이드 롱·숏·확신도·변이 관점), `news.js`(중요도 1~2). 마스터 노션 Informations의 IB 리포트 요지(라이선스 — 문장 복제 금지, 출처·요지만).
- 제외 원천(robots·약관): 레딧·ValueInvestorsClub·StockTwits·X(유료 API 승인 대기)·사이트 직접 접속(Seeking Alpha·Motley Fool). 레딧 글은 마스터가 크롬 확장으로 넘긴 것만.

- 판단 틀: `knowledge/narratives/lens_semianalysis.md`(SemiAnalysis 렌즈 L1~L7·크라우딩, 마스터 지시 2026-10-28) — 내러티브를 '병목·TCO·바텀업 숫자'로 바꿀 수 있는지가 1순위 질문.

## 2. 거르기
- 제목에 종목명·티커·핵심 제품이 없는 일반 시황 기사는 버린다(색인 검색이라 잡음이 섞인다). 같은 사건 재인용은 하나로(`origin_id` 원칙).
- 채널을 구분해 센다: 커뮤니티(개인·독립 분석가) / IB(목표가·등급) / 회사(콜·보도자료) / 언론.

## 3. 쓰기 — `knowledge/narratives/companies/<id>.md`
```
---
id: co-…
as_of: YYYY-MM-DD
summary: (한 줄 — 지금 멀티플을 결정하는 1순위 내러티브와 단계)
stage: 태동|확산|컨센서스|과밀|소멸|붕괴
crowding: 낮음|중간|높음
alpha_effect: {gap: +n|−n|0, upside: +n|−n|0}   # 알파 판단 보정 제안(점수 아님)
---
## 섹터 멀티플을 결정하는 내러티브 (상위 3~5)
| 내러티브 | 바뀌는 가치 입력(TAM·점유율·마진·재투자·위험) | 방향(프리미엄/디스카운트) | 근거(채널·건수·대표 제목·날짜) | 단계 |
## 기업 고유 내러티브 (프리미엄·디스카운트 요인)
## IB 커버리지 흐름 (최근 60일: 개시·상향·하향·목표가 방향)
## 커뮤니티 논조 (강세·약세 대표 논지 각 1~2개, 개인 식별 정보 없이)
## 숫자로 바꾸기 — v2 동인에 주는 의미 (시나리오 확률·성장·마진·멀티플 범위)
## 반증 조건·확인할 KPI (멀티플이 바뀔 사건)
```
- 단계 기준(framework.md §7): 태동(언급 적고 가속, 리비전 없음) → 확산(언급↑, 리비전 시작) → 컨센서스(언급 많고 정체, 숫자 반영) → 과밀(언급·프리미엄 최고, 가격이 리비전 앞섬) → 소멸 → 붕괴(반증).
- 알파 연결: 과밀·컨센서스면 gap을 낮추고, 태동·확산 + 숫자 전환 직전이면 upside·gap을 높이는 쪽으로 제안한다. 실제 점수 변경은 tenbagger-card '알파 점수' 절에서 이유와 함께.
- 등록부: 섹터 내러티브가 `knowledge/narratives/registry.yaml`에 없으면 키워드(영·한)·노출 기업·반증 조건과 함께 추가한다.

## 금지
- 커뮤니티 글을 사실로 쓰기, 개인(작성자) 이름·계정 저장, 유료 본문·IB 리포트 문장 복제, robots·약관이 막은 원천 자동 수집, 목표주가를 결론처럼 인용(IB 목표가는 '기대의 증거'로만).
