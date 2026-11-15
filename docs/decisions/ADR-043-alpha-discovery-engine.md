# ADR-043 — 알파 발굴 엔진: 전 섹터·7개 시장·다채널 단서 장부와 채널 성적표(2026-11-15)

마스터 지시(2026-11-15): "Chiip의 종목 발굴 시스템 전반을 점검하고 보완할 부분을 고도화하라. AI 밸류체인에 국한하지 말고 산업, 섹터 전반에서 알파가 높은 종목을 찾는 프로세스 … 월스트리트 IB 리서치 하우스의 접근 방법과 프로세스를 접목 … 관련 자료를 방대하게 조사한 이후 … 미국, 일본, 유럽연합, 영국, 대만, 홍콩, 한국 … 행동주의 표적, SPAC 상장, 국장 테마주, 패니메이 & 프레디맥과 같이 구루 포지션을 따라가는 전략, 텐배거 조짐이 보이지만 아직 수급이 몰리지 않고 리테일과 기관으로부터 관심을 덜 받고 있는 종목 등 다양한 종목 발굴 채널".
설계·근거: `knowledge/methods/discovery_engine.md`(조사 8건 요지 — IB 절차·이상현상·행동주의·SPAC/IPO·구루·국장 테마·저관심 10배·특수 상황).

## 문제
- 발굴은 테마 지도 → 병목 → 공급사(AI 밸류체인)가 중심이었다. 비AI·해외는 스크린 보조뿐이었다(섹터 순환 미국 18섹터, 아시아 전자 3시장).
- 행동주의·구루·국장 테마·특수 상황 채널이 없었다. 13F는 기관 수 순위만 냈다.
- 채널마다 결과 파일이 따로라 같은 종목에 신호가 겹쳐도 몰랐고, 채널별 적중률을 잴 수 없었다.
- 선별 점수는 빈칸을 중립 5.0으로 채워 약한 종목을 부풀릴 수 있었다.
- SPAC 기저율 '시세 표본 99건'은 history.csv 시세 칸이 모두 비어 재현되지 않았다.

## 결정
1. **단서 장부** `scripts/discovery/leads.py`. 모든 채널 단서를 탐지일·가격과 함께 덧붙이기만 한다(`leads.csv`). 상태 변화와 무효는 `leads_events.csv`에 남긴다.
   - 성적표 `--scorecard`: 같은 시장 지수 대비 30·91·182·365일 초과수익. 미국 $10B 미만은 IWM, 코스닥은 KOSDAQ과 비교한다. 적중률은 Beta(10,10)로 축소하고, 채널 선별 통과·기각을 나눠 잰다(후회 측정). 30건 전에는 다시 맞추지 않는다.
2. **채널 등록부** `config/discovery_channels.yaml`. 채널·종류별 사전값(기대 초과·기간·sd·출처)은 문헌 효과에 게재 뒤 감쇠 0.5를 곱한 값이다. 경보 규칙과 지수도 여기 둔다.
3. **채널**
   - **행동주의**: 미국 13D·위임장 서류, 한국 5% 일반 서식·주주 측 의결권 권유, 일본 EDINET(키 대기), 표적 유사도 스크린. 명단 `config/activists.yaml`.
   - **구루**: 명단 45곳 13F(GuruScore — 최고 확신·순위·기밀 공개·쏠림 감점), 13D·13G, 공개 포트폴리오 페이지, 패니·프레디형 논지 장부(`config/special_situations.yaml`).
   - **특수 상황**: 공개매수·13E3·분할, 한국 소각·취득·밸류업, JPX 자본비용 공시 갱신, 대만 第35款.
   - **국장 테마**: `scripts/discovery/kr_theme.py`. 점화·확산·과열·소멸·구조적 확인을 판정하고 KRX 투자경고(내부 표지)·DART 적신호를 쓴다.
   - **저관심 10배 전조·IB 정량 복합**: `scripts/discovery/channel_screens.py`. 7개 시장 순번이고 시장별 기저율을 함께 붙인다.
4. **채널 선별** `scripts/discovery/channels.py`. 종목별로 채널 최고 강도에 겹침 가점을 더하고 적신호 감점을 뺀다.
   - '② 채널 선별' → 판단 카드(새 채널 렌즈 5개 `knowledge/methods/sector_lenses/activism·guru·special·kr_theme·multibagger.md`) → 발굴 선별(screen.py '채널: <이름>' 테마) → 위원회 메모 → `--promote`(채널 후보도 받는다).
   - Pulse는 '발굴 채널' 분류로 등록부 경보 규칙을 넘은 새 단서만 받는다.
5. **IB식 관문**: 위원회 메모 머리말 검사기 `scripts/discovery/memo_check.py`.
   - 변이 관점: 합의와 max(1σ, 10%) 이상 다른 동인
   - 시나리오 확률과 상방÷하방 2.0 이상
   - 365일 안 촉매
   - 사전 부검 3개, 킬 조건 2개
   - 기저율 분위(90분위 초과 경고)
   - 만료 365일
   - red-team 답
   - 선별 점수는 빈칸이 2개를 넘으면 상한 5.9다(`screen.py`).
6. **약관·robots로 쓰지 않는 원천**(새 채널): Google News RSS(robots 금지·ClaudeBot 차단), HKEXnews(이용약관 5조), 영국 인수위원회 공시표(robots ClaudeBot 금지), FCA NSM(서면 동의), BaFin 포털·TDnet·옛 MOPS·네이버 금융.
   - 기존 파이프라인의 Google News·HKEXnews 사용은 마스터 결정 대기다(TODO_MASTER 21-53).

## 결과
- 단서 장부가 생겨 채널마다 성적표를 낼 수 있다. 가중은 표본 외 검정(`scripts/fit/stepwise.py`)으로만 바꾼다.
- 결정론 수집이 늘었다(run_hourly에 공시 60분·구루 13F 360분·테마 언급 1440분). TradingView 호출(스크린·국장 급등)은 모델 몫이라 응답 행 수를 40~50행으로 줄였다(토큰 비용).
- 개발 중 정시 수집이 미완성 코드로 한 번 돌아 옛 구루 점수식 단서 4건이 장부에 들어갔다 — 지우지 않고 'void' 사건으로 무효 처리했다.

## 남긴 것
- EDINET 키(일본 행동주의·TOB), data.go.kr 주식시세 활용신청(한국 전 종목 일봉·동반 상승 군집), KRX Open API 키
- SPAC 기저율 재계산(history.csv 시세 재수집), SPAC 점수 개선(조사 D: 시간 압박·스폰서·매출 규모·관심 0 — 이번에는 기록만)
- 13F 가치 칸 저장(VIP식 쏠림), 미국 Form 4 내부자 매수 군집, 대만 10% 이상 보유자(TWSE t187ap02_L), Fairholme 등 등록 펀드 N-PORT

## 후속(2026-11-15) — 빈 채널 두 개
위 '남긴 것' 중 13F 가치 칸·VIP 쏠림, 내부자 매수 군집, Fairholme N-PORT를 채웠다(대만 10% 보유자는 남음). 설계 요지는 `knowledge/methods/discovery_engine.md` §4.2·§4.5b에 있다.
1. **내부자 매수** `radar/insider_buys.py`(run_hourly 60분, 회차 6분 예산, 건강 id = 재시도 키 `src-insider-buys`).
   - 미국: efts Form 4 → 원문 XML 코드 P. 한국: OpenDART 소유상황보고서 → elestock 증감 → 원본 보고사유 01.
   - 기회형만 남긴다. Cohen·Malloy·Pomorski 2012 일상형(앞선 3년 같은 달 거래)은 원문으로 확인해 뺀다. 이력이 모자란 내부자는 기회형(이력 부족)으로 둔다.
   - 10b5-1·거래계획·공모 참여·늦은 제출·펀드형 발행사·소액도 뺀다.
   - 30일 안 2명 이상은 `cluster`, CEO·CFO 단독은 `ceo`다. 규칙은 `channels.insider.rules`, 등록부 prm-insider-* 26개다.
2. **13F 가치 칸** — `thirteenf_market.info_table`이 [주식 수, 이름, 가치]를 저장한다. `aggregate()`는 옛 두 칸 캐시도 읽는다.
3. **VIP 쏠림** — `thirteenf_market.vip`(GS VIP 규칙 복제: 10~200종목·$10M·상위 10·바구니 50)을 `guru13f.crowding`이 쓴다.
   - 상위 10 비율 15% 이상이면 −0.3, 바구니는 강도 상한이다.
   - 가치 칸 기관이 85% 미만인 분기는 예전 근사(보유 기관 비율)로 대신한다. 그래서 2026Q4부터 VIP를 실제로 쓴다. 등록부는 prm-guru-crowd-vip-* 9개다.
4. **Fairholme N-PORT** — `guru13f.nport`가 주 1회 N-PORT-P를 보고 논지 종목(cusip6)과 맞는 보유를 `knowledge/models/guru/thesis_evidence.json`에 남긴다. 기준선 뒤 변화만 guru/thesis 단서다. 등록부는 prm-guru-nport-* 4개다.
5. **첫 실수집 정정** — 점수식 수정 전 단서 17건을 void했다. 16건은 탐지일로 다시 넣었다. 같은 키·같은 날짜로 다시 넣으면 lead_id가 void와 겹친다.
   - 11-15 04시 구루 정정 때 다시 넣은 MCO·BRK.A 2건이 이 겹침으로 여전히 무효다(leads.py 후속 과제).
6. 시험: `tests/test_insider_vip.py` 27개(네트워크 흉내).
