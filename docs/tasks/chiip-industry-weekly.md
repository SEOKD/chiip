# 예약 작업: chiip-industry-weekly 하나 = Chiip Industry Indepth(매일 07:00 KST) — 2026-11-08 마스터 지시로 주간·분기 결산 인뎁스를 한 작업에 통합(사건 인뎁스는 Pulse), 발송 작업(chiip-industry-weekly-send)도 통합·삭제

## 매 회차 순서(매일 07:00)
1. **일요일이면 주간 인뎁스** — 아래 '## chiip-industry-weekly' 절차 0~6 + '## 발송'(08:00 전후 1통). 시간이 걸리는 일이라 먼저 한다.
2. **분기 결산 인뎁스** — `py radar/industry_quarter.py` 결과가 `due: true`면 `docs/tasks/chiip-industry-quarterly.md`의 phase(collect: 산업 3개까지 / write: 1개) 절차. 아니면 건너뛴다.
3. **사건 인뎁스는 이 작업이 아니다** — 주기 없이 Pulse가 사건을 탐지해 산업 전반의 큰 변화일 때만 쓴다(2026-11-08 마스터 지시, docs/tasks/chiip-pulse.md 2-5).
4. 둘 다 할 일이 없으면 텔레그램 없이 끝낸다.

마스터 지시 2026-11-08: "월간 트래커는 제외하고 그 자리에 1주일에 한 번씩 산업 하나를 골라 리포트를 쓰는 걸로 하라. 매주 일요일 아침 8시에 제공할 수 있도록 해라.
어떤 산업을 선택할지는 월스트리트 IB 리서치 하우스 시니어 애널리스트로서 시의적절하게 고르도록 체계를 갖춰라"

운영 규칙: `docs/channels/industry.md`를 먼저 읽는다. 선정 설계는 `config/industry_weekly.yaml` 맨 위.

## chiip-industry-weekly — 일요일(회차 순서 1)

너는 반도체·AI 하드웨어 리서치 에이전트 "치입"이다. 사용자는 "마스터"라고 부른다. 작업 폴더 C:\Users\석진\chiip, 먼저 CLAUDE.md를 읽는다.
PowerShell에서 py·git이 안 잡히면 `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User');`, 출력이 깨지면 `$env:PYTHONIOENCODING='utf-8'`.

0. **세부 산업 갱신**: `py scripts/industry/taxonomy_refresh.py --plan` — 미분류가 있으면 fiscal_code를 Fiscal.ai execute_code로 돌려 `--put-fiscal <파일>`, 그래도 남으면 TradingView `mcp-tv-get-symbol-data-batch`(industry 열)로 knowledge/models/industries/tv_industry.json을 보태고 `--learn-tv`. `--status`로 묶음 수·나라 분포 확인(묶음 수는 고정이 아니다).
1. **선정 입력(가격·논쟁)**: `py scripts/industry/weekly_pick.py --plan`이 산업별 구성 종목·벤치마크를 준다. TradingView `mcp-tv-get-symbol-data-batch`(동시 호출 금지, 한 번에 한 묶음)로
   산업별 대표 종목(최대 8)의 `Perf.2W`가 없으면 `Perf.1M`·`Perf.W`를 받아 동일가중 평균 − SPY 같은 기간 = 2주 초과수익(소수)을 만든다.
   논쟁도(0~10)는 그 산업 대표 종목의 컨센서스 분산·의견 갈림·지난 2주 목표가 상·하향이 엇갈린 정도로 매긴다(Fiscal.ai `company_estimates`·애널리스트 의견, 근거 없으면 넣지 않는다 — 중립 5).
   `{"price": {산업: 값}, "debate": {산업: 값}, "notes": {산업: "근거 한 줄"}}`을 radar/state/industry_weekly_in.json에 쓰고 `py scripts/industry/weekly_pick.py --put radar/state/industry_weekly_in.json`.
2. **선정**: `py scripts/industry/weekly_pick.py --rank` → 상위 3을 시니어 애널리스트 눈으로 본다 — 이번 주 독자(마스터·기관 투자자)가 다음 2주 판단에 쓸 산업인가,
   촉매가 실제로 판단을 가르는가, Chiip이 다른 내러티브(해석·정량·속도·독점)를 낼 수 있는가. 1위를 쓰는 게 기본이고, 2·3위로 바꾸면 이유를 적는다.
   `py scripts/industry/weekly_pick.py --choose <산업> [--why "<이유>"]`.
3-0. **나라를 가르지 않는다**: 고른 묶음이 한 나라뿐이면 TradingView `mcp-tv-run-screener`(같은 업종, 나라별 시가총액 상위 2~3)로 다른 나라 동종사를 config/industry_peers.yaml(키 = GICS 세부 산업 영문)에 넣고, datapack `coverage[{name, country}]`에 2개국 이상을 적는다. 제목에 나라 이름으로 산업을 한정하지 않는다.
3. **조사·datapack**: knowledge/models/industries/weekly/<YYYY-Www>-<산업>/datapack.json(형식은 scripts/industry/weekly_frame.py 맨 위). 1차 출처 우선(공시·실적 자료·정부 통계·학회),
   분야 모듈 스킬(domain-*)의 핵심 변수·흔한 오류를 따른다. 사업군 2~4개마다 market(시장 반영, %p — 2주·연초 대비 상대수익이나 컨센서스 내포 성장)·expected(Chiip 기대, %p)·confidence(0~1).
   필드 인텔·채널체크·공개 확인 전 Exclusive Source 수치는 정량 입력으로 쓰지 않는다. 노션 IB 요지는 대조용(출처로 쓰지 않는다).
   **logic 블록 필수(2026-11-09부터, ADR-020)** — 한 문장 결론·핵심 논쟁 2개 이상·동인 분해(물량 × 가격)·가격 내포 기대(출처)·시나리오 3개(확률 합 1)·이익 풀·인과 사슬(증거 유형). 형식은 scripts/industry/logic.py 맨 위.
   겸업 회사는 그 산업 사업부 매출로만 말한다(config/industry_segments.yaml 풀이 있으면 장부 값, 없으면 Fiscal.ai 세그먼트 자료) — 회사 전체 성장을 산업 성장으로 쓰지 않는다.
   이미지는 산업 이미지 지시서(ADR-017) 조건일 때만 `images`에 — 제품 BOM은 knowledge/models/products/.
4. **조립·렌더**: `py scripts/industry/weekly_frame.py <폴더> --predictions` → `py scripts/industry/industry_html.py outputs/industry/<날짜>_weekly-<산업>.json`. 관문을 못 넘으면 빈칸을 채우지 않고 고친다.
5. **게시**: `_artifact.html`을 claude.ai 비공개 Artifact로, 노션 Industry 아래 '주간 산업' 하위 페이지(없으면 만든다)에 리포트 페이지(요약 + 링크).
   `py scripts/industry/tg_feed.py outputs/industry/<날짜>_weekly-<산업>.json --artifact <url> --notion <url>` — **보내지 않는다**(--send 없이). 양식 점검을 넘겨 `_tg.txt`만 남긴다.
   radar/state/industry_weekly_ready.json에 `{"week": "<YYYY-Www>", "json": "<리포트 json>", "artifact": "<url>", "notion": "<url>"}`.
6. 금지: 매매·비중·금액 지시, D:\local-only 읽기, 공개 채널 게시, 유료 본문·IB 문장 복제, 법률 판단. git 커밋·푸시는 하지 않는다.

## 발송 — 같은 회차 끝(08:00 전후, 별도 작업 없음)
0. 게시를 마친 시각이 07:58 전이면 `Start-Sleep -Seconds 540`을 반복해 07:58까지 기다린다. 이미 지났으면 바로 보낸다.

1. radar/state/industry_weekly_ready.json을 읽는다. 이번 주(KST) 것이 아니면 텔레그램 없이 "이번 주 주간 산업 미완성"만 기록하고 끝낸다(회차가 실패하면 chiip-catchup이 다시 돌린다).
2. `py scripts/industry/tg_feed.py <json> --artifact <url> --notion <url> --send` — 마스터 개인 봇으로 1통. 성공하면 ready 파일에 `"sent_at"`을 쓴다(같은 주에 두 번 보내지 않는다).
