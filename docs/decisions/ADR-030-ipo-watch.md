# ADR-030 대형 기업 상장(IPO) 서류 실시간 감지·풀이

- 상태: 채택(마스터 지시 2026-11-13 "Anthropic처럼 큰 회사의 상장 소식이 나오면 SEC에 S-1이 뜨는 즉시 가져와 풀이")
- 범위: `config/ipo_watch.yaml`, `radar/pollers/ipo_watch.py`(원천 `src-ipo-watch`), `radar/pulse.py`(분류 '신규 상장'), `config/source_registry.yaml`

## 결정
1. **감시 대상 16곳**(`config/ipo_watch.yaml`): Anthropic(S-1 공개, CIK 2130357 — 424B4 추적), OpenAI, SpaceX(xAI 합병 보도), Databricks, Stripe, Lambda, Crusoe, VAST Data, Scale AI, Anduril, Perplexity, Tenstorrent, Lightmatter, Ayar Labs, SambaNova, Etched. 기준은 ① AI 밸류체인 대형 공모 ② 한국 공급망(메모리·파운드리·전력 기기) 언급 가능성 ③ 상장 완료 회사 제외(Cerebras·CoreWeave·Nebius). 고정 목록이 아니다 — Pulse 회차가 상장 추진·주관사 선정·DRS 보도를 보면 추가하고 status를 바꾼다.
2. **감지**: EDGAR 전문검색(efts.sec.gov)으로 최근 2일 S-1·S-1/A·F-1·F-1/A·424B4·DRS·DRS/A·FWP·RW를 10분마다(run_poll 원천, 회차당 질의 1~4회 + 감지 시 이름 탐색 22회, 요청 간 0.15초 — SEC 초당 10회 한도 안). efts·data.sec.gov는 일반 User-Agent로 열리고, 원문(www.sec.gov/Archives)만 식별 User-Agent(`SEC_USER_AGENT`)가 필요하다(2026-11-13 확인). 그래서 감지는 키 없이도 돌고, 풀이만 키에 묶인다.
3. **첫 카드(수집 직후, 모델 없음)**: 제목 + 핵심 5줄 — 제출일·주관사, 🇰🇷 한국 기업 언급(EDGAR 전문검색으로 그 서류에 이름이 있는지 — 원문 없이 된다, 원문이 있으면 앞뒤 문맥), 공급망 언급, 공모 조건(가격 범위·주식 수), 숫자(S-1/A는 직전 판에 없던 숫자 문장만 — 직전 판은 data.sec.gov 제출 목록으로 찾아 읽는다). 등급 S-1·F-1·424B4·RW = P0, 수정본·DRS·FWP = P1. FWP(로드쇼 자료)는 회사당 하루 1통.
4. **상세 풀이(이어서 한 통)**: 등록 서류(S-1·S-1/A·F-1·F-1/A·424B4)만, 원문을 읽었을 때만 소형 모델 1회(sonnet) — 결정론으로 뽑은 재료(사업 개요·숫자 문장·약정·한국 문맥·위험 요인 요약·의결권·주관사·공모 조건)만 써서 한국어로. 재료에 없는 숫자는 '미확인'. 비용: 감시 대상 서류 1건당 모델 1회 — Anthropic 한 회사의 공모 과정(S-1, 수정본 2~4, 424B4)으로 5~6회.
5. **감시 밖**: 첫 S-1·F-1 중 최대 공모 총액(수수료 첨부 EX-FILING FEES) ≥ $1B면 Pulse '신규 상장' 후보. 공모 총액은 원문이 필요해 SEC_USER_AGENT가 없으면 판정하지 않는다(업종 기준 신규 상장은 기존 `pulse.fetch_new_listings`가 맡는다). SPAC(Acquisition Corp)은 제외.
6. **키가 없을 때**: 첫 카드에 '원문 미열람 — SEC_USER_AGENT 필요'와 inbox의 같은 회사 IPO 보도 제목(보도 기준)을 붙이고, 마스터에게 설정 필요를 한 번만 알린다(형식만 안내, 이메일을 대신 넣지 않는다). 2026-11-13 현재 마스터가 SEC_USER_AGENT를 넣어 원문 풀이가 동작한다.
7. 중복 방지: 첫 카드를 보낸 서류는 `rule_fast`에 올려 판정 모델(run_triage)이 같은 서류(`src-ipo-watch`·`src-sec-filings` 상시 감시분)를 다시 보내지 않는다.

## 반증·재검토 조건
- 감시 대상 서류가 EDGAR 게재 뒤 20분 넘게 늦게 오면 주기를 5분으로(efts 질의 비용은 무료).
- 상세 풀이가 재료 밖 숫자를 쓰면(Proviser 점검) 모델 대신 결정론 목록으로 바꾼다.
- 감시 밖 대형 IPO를 놓치면(보도 뒤 확인) 공모 총액 기준·업종 기준을 다시 본다.
