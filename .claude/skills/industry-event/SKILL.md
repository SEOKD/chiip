---
name: industry-event
description: Chiip Industry Report '사건 때 심층'. 선거·규제·정책 같은 사건이 산업을 흔들 때 마스터의 논리 구조로 쓴다 — 시장의 명목 해석 ↔ 이해관계자 돈의 흐름(양당) ↔ 지연 유인 vs 실행 압력 ↔ 실행 시계 → 사업군 갭 → 산업 판단 등급. 마스터 요청 또는 판단을 바꾸는 사건 때.
argument-hint: "[사건 id]"
---

# industry-event — 사건 때 심층 (마스터 지시 2026-11-08)

운영 규칙 `docs/channels/industry.md`, 논리 틀 `config/industry_event.yaml`, 엔진 `scripts/industry/event_frame.py`, 렌더 `scripts/industry/industry_html.py`.

## 마스터의 논리 구조(고정)
1. 시장은 사건을 **명목적으로** 읽는다(예: "블루 스윕 = 데이터센터 제동"). 그 해석이 가격에 얼마나 들어갔는지 먼저 잰다.
2. 그러나 정치인은 규제산업의 **돈**(로비·PAC·슈퍼 PAC)을 양당 모두 받는다. 데이터로 확인한다 — 확인 못 하면 쓰지 않는다.
3. 정치인에게는 **시간을 끌 유인**(규제 위협을 유지할수록 자금이 이어진다 — 예: CLARITY법)과 **결과물을 보여야 할 압력**(로비 자금의 한계, 공약, 유권자)이 함께 있다.
4. 결과물은 **선거·취임 직후**에 몰린다(예: 트럼프 2기 첫 100일 행정명령). 어느 경로(주·연방 의회·기관·행정부)가 어느 단계에서 언제 움직이는지 시계로 그린다.
5. 그래서 실제 영향은 명목 해석과 다를 수 있다 — 사업군마다 Chiip 기대 영향(Σ 확률 × 영향)과 시장 반영의 갭을 잰다.

## 절차
1. **사건 확인:** 결과·발표를 1차 출처(AP 콜·관보·규제기관 보도자료)로 확인한다. 보도마다 다르면 '미확인'으로 둔다.
2. **시장 반응:** 사업군(4~6개)을 정하고 종목 1주 변화(TradingView `change|1W`, 벤치마크 대비 %p)와 업종 ETF 시장 모형 CAR(`radar/markets/midterm.py` 같은 관측이 있으면 그것)을 넣는다. 같은 기간 다른 큰 사건이 겹치면 `reaction.confound`에 적는다(확신도가 깎인다).
3. **돈의 흐름(양당 필수):**
   - 로비: Easyconomics `insider_and_politics` lobbying(하원 LD 분기 집계)
   - 기업 PAC 정당별: `py radar/usgov/fec_money.py`(설정 `config/fec_pacs.yaml`에 그 산업 PAC 추가)
   - 슈퍼 PAC: 1차 보도·FEC 공시를 출처와 함께
   - 관문은 민주·공화 양쪽으로 간 돈이 확인돼야 넘어간다 — 가설을 확인만 하는 편향을 막는다.
4. **지연 vs 실행:** 각 근거에 출처를 붙인다. 이론 근거(McChesney 1987 지대 추출, Hall·Deardorff 2006 입법 보조금, Ansolabehere 외 2003)는 그대로 인용한다.
5. **실행 경로:** 경로마다 수준(주·연방 의회·연방 기관·행정부)과 현재 단계(`config/industry_event.yaml` stages — 금지표대로 발의를 시행으로 쓰지 않는다), 주체, 창, 12개월 실행 확률, 사업군 영향(%·가정)을 적는다. 실행 시계(취임·회기·마감·규칙 시행일)와 선례를 붙인다.
6. **반대 검증:** 마스터 가설을 같은 강도로 때린다. 최소 3개, 출처 포함.
7. **체크포인트:** 날짜·측정값·확률·'맞으면 가설 지지/반대'를 3개 이상 적고 `--predictions`로 예측 장부에 올린다.
7-1. **이미지 판정(2026-11-08 마스터 지시, ADR-017):** 절마다 산업 이미지 지시서 1절 조건(구조·병목 위치·세대 비교·생소한 제품·공급사 지도) 중 하나에 해당하면 datapack `images`에 `{section, product, condition, view?}`를 적는다 — 리포트당 최대 3장(분해도 2). 숫자·가격·수급이 논지인 절은 넣지 않는다. 제품 BOM은 `knowledge/models/products/<slug>/bom.json`(README 형식, '확인' 6개 미만이면 표만). 초안 단계에 `py scripts/tenbagger/product_images.py make --product <slug> --batch`(세대 비교는 `<a>,<b> --pair`, 패키지·적층은 `--view cross-section`), 회수 뒤 `image_check.py run --product <slug>` → Read로 보고 `visual` → 승인은 자동(auto_approve). 산업 몫은 장부 한도의 40%. 판정 기록은 리포트 JSON `image_plan`에 남는다.
8. **조립·렌더:** datapack은 `knowledge/models/industries/events/<id>/datapack.json`이다. 아래 명령으로 조립하고 렌더한다.
   ```
   py scripts/industry/event_frame.py <id> --predictions
   py scripts/industry/industry_html.py outputs/industry/<날짜>_<id>.json
   ```
   관문을 못 넘으면 멈춘다 — 빈칸을 채우지 않는다. 등급은 규칙이 계산하고(갭 ±5%p, 확신도 0.5), 토론으로는 `debate`에 이유를 적어 한 단계까지만 바꾼다.
9. **게시:** `_artifact.html`을 claude.ai 비공개 Artifact로 게시한다. 노션 `Industry` 아래 산업 하위 페이지에 리포트 페이지(요약 + 링크)를 만들고, 마스터 개인 텔레그램으로 알린다 — 글은 손으로 쓰지 않고 `py scripts/industry/tg_feed.py outputs/industry/<날짜>_<id>.json --artifact <url> --notion <url> --send`가 리포트 JSON에서 조립한다(2026-11-08 마스터 지시 "텔레그램 피드로 제공할 때 글이 가독성 있게": 제목 → 등급별 판단 → 핵심 Q&A 한 줄씩 → 숫자 4개 → 다음 확인 날짜·확률 → 링크). 양식 점검(줄 길이)을 못 넘으면 보내지 않는다.

## 쓰지 않는 것
- 매매·비중·금액 지시. 등급은 산업 판단이다.
- 법률 판단. 정치인·정당에 대한 가치 판단(분석은 유인과 데이터로만).
- 보도 제목을 사실로. 정책 단계를 건너뛴 단정.
