# 텐배거 판단 체계 — 구루의 사고 논리와 2020년대 증거 (2026-11-21)

> 마스터 지시(2026-11-21): "Ten-bagger 종목을 발굴할 수 있는 사고 논리와 판단 체계, 리서치 방법론에 대해 최신 기법을 조사하고 이를 시스템 기반에 업데이트할 수 있도록 하라. 스탠리 드러켄밀러, 베일리 기포드, 론 바론, 피터 린치, 워렌 버핏 등 글로벌 구루의 투자 논리를 학습하고 2026년 또는 2020년대 최근 시장 역학과 투자 성공 방정식도 참조하라."
> 설정 `config/tenbagger_playbook.yaml` · 계산·검사 `scripts/tenbagger/playbook.py` · 관문 `scripts/discovery/memo_check.py` · 결정 기록 `docs/decisions/ADR-050-tenbagger-playbook.md`
> 출처 등급: **[V]** 이번에 1차 원문을 열어 확인 · **[S]** 2차 요약·보도(원문 미대조) · **[M]** 기억(미검증 — 확인 전에는 근거로 쓰지 않는다). 발굴 채널·학술 근거의 기존 정리는 `knowledge/methods/discovery_engine.md`.

## 0. 결론 — 무엇이 바뀌나
1. **10배는 '높은 연 수익률'이 아니라 '오래 끊기지 않는 복리'에서 나온다.** 미국 역대 최고 누적 수익 17종목의 연 복리는 평균 13.47%였다 [S, Bessembinder 2024]. 10배에 필요한 속도는 5년이면 연 58.5%, 10년이면 25.9%, 20년이면 12.2%다(산술). 기존 위원회 메모는 12개월 시나리오와 365일 촉매만 물었다 — 5~10년 경로를 묻는 관문이 없었다.
2. **출발점은 대개 '싸고, 이미 이익을 내는, 작은 회사'다.** 2012~2022년 10배 446종목 중 82%가 출발 때 흑자였고 절반은 EV/매출 1배 미만·EV/EBIT 10배 미만이었다 [S, Eyesan 2023]. 미국 464종목 연구도 FCF 수익률·B/M이 가장 큰 계수였다 [기존 정리, Yartseva 2025].
3. **엔진은 둘이다 — 이익 성장 × 배수 확대.** 446종목의 72%는 매출 성장이 연 20% 미만이었고, 흑자 승자의 74%는 이익이 매출보다 빨리 컸다 [S]. 매출 고성장은 필요조건이 아니다. 이익률 개선과 재평가가 함께 돌아야 한다.
4. **해자와 재무 건전성이 복리를 지킨다.** 2015~2020년 5년 350% 이상 104종목 중 80%에 진입장벽, 88%가 건전한 재무에서 출발했다 [S, Alta Fox 2020].
5. **찾는 것만큼 들고 가는 것이 어렵다.** 1985~2024년 미국 6,500종목의 중앙 낙폭은 85%, 고점에서 저점까지 2.5년, 절반 넘게 전 고점을 회복하지 못했다. 최고 종목도 큰 낙폭을 겪는다 [V, Mauboussin·Callahan 2025 요약 페이지]. 드러켄밀러는 2026년 인터뷰에서 엔비디아를 일찍 판 것을 후회했다 [S].
6. **그래서 세 가지를 시스템에 넣었다.** ① 여섯 관점 **구루 교차 점검**을 위원회 메모 관문으로(2026-11-22 메모부터) ② 채널 성적표에 **2·3년 기간과 오른쪽 꼬리 지표** ③ **낙폭 재심사**(가격이 아니라 투자 논리 지표로 유지·종료를 가른다).

## 1. 구루별 사고 논리와 Chiip 반영
| 구루 | 핵심 논리(자기 말 요약) | 등급·원전 | 반영한 관점 |
|---|---|---|---|
| 스탠리 드러켄밀러 | 지금 실적이 아니라 **18개월 뒤 그림**에 값이 매겨진다. 시장 전체는 이익보다 **유동성(연준)**이 움직인다. 확신이 있으면 집중한다. 먼저 사고 조사한다("Invest, then investigate"). 가장 큰 실수는 **너무 일찍 판 것** | 18개월 [S, Benzinga 2025 인용] · 유동성 [M] · 조기 매도 후회·"큰 변화는 투자자가 따라가지 못한다" [S, Morgan Stanley Hard Lessons 2026-02-27 보도] | 변화의 방향(change) · 유동성 국면 · 보유 규율 |
| 베일리 기포드(LTGG) | **10년 지평**. 주식의 가장 좋은 점은 상방에 한도가 없다는 것(비대칭). 10문항 조사 틀: 5년 매출 2배 여지 → 10년 뒤 → 경쟁우위 → 문화 → 고객·사회 → 수익률과 그 방향 → 자본 배분 → **5배 경로** → **시장이 왜 모르나** | 지평·비대칭·30~40종목 [V, 전략 페이지] · 질문 1~3 [S, 공식 문서 발췌] · 질문 4~10 [M — 원문 PDF는 내려받기가 필요해 미대조] | 성장 여지(runway) · 5배 경로(mispricing) · 판단 기간 |
| 론 바론 | **5~6년에 2배**(연 12~15%)가 될 사업을 사서 오래 든다. 경쟁우위가 있고 **뛰어난 사람**이 경영하는 회사. 지금 값이 아니라 5~10년 뒤 가치로 본다 | [S, Kiplinger 2022·Baron Capital 사이트(현재 문구는 5~7년)] | 사람과 문화(people) · 재투자 복리 |
| 피터 린치 | 크기 먼저, 다음 '이야기'로 6분류. 10배는 고성장주·회생주·경기순환주에서. PEG. 50% 올랐다고 팔지 않는다 | 기존 반영 — ADR-048, `scripts/tenbagger/lynch.py` | 5배 경로(분류·PEG) · 보유 규율 |
| 워렌 버핏 | **소유주 이익** = 이익 + 감가상각 등 비현금 비용 − 경쟁 지위 유지에 필요한 설비투자. **유보 1달러가 시장가치 1달러 이상**을 만들 때만 유보가 옳다. 높은 자본수익률을 지키는 해자 | 소유주 이익 [V, 1986 서한] · 1달러 시험 [V, 1984 서한] · 해자 [M, 2007 서한 미대조] | 해자와 자본수익률(moat_returns) · 재투자 복리(reinvestment) |

구루들이 겹치는 곳: ① 긴 기간 ② 경쟁우위 ③ 사람 ④ 재투자할 곳 ⑤ 일찍 팔지 않기. 갈리는 곳: 드러켄밀러는 **변화의 속도와 유동성**에, 버핏은 **변하지 않는 것**에 건다. 한 관점만 통과한 종목은 그 관점의 맹점을 안는다 — 그래서 교차 점검이다.

## 2. 2020년대 증거 — 숫자로 본 성공 방정식
| 연구 | 표본 | 핵심 숫자 | 등급 |
|---|---|---|---|
| Bessembinder 2024 'Which U.S. Stocks Generated the Highest Long-Term Returns?' | CRSP 29,078종목, 1925-12~2023-12 | 51.6%가 누적 손실. 17종목이 누적 5,000,000% 초과, 그 연 복리 평균 13.47%(최고 Altria 16.29%) | [S] |
| Mauboussin·Callahan 2025 'Drawdowns and Recoveries' | 미국 6,500종목, 1985~2024 | 중앙 낙폭 85%·고점→저점 2.5년, 절반 넘게 전 고점 미회복. 최고 종목·투자자도 큰 낙폭 | [V] 요약 · 최고 종목 중앙 낙폭 72%·회복 4.3년은 [S] |
| Eyesan 2023 'Global Outperformers' | 14,090종목 중 2012~2022 10배 446종목(3.16%) | 82% 출발 때 흑자 · 72% 매출 성장 연 20% 미만 · 50% EV/매출 <1배·EV/EBIT <10배 · 59% 아시아(인도 91) · 직전 10년(2002~2012)은 300종목 | [S] |
| Alta Fox 2020 'The Makings of a Multibagger' | 시총 $150M~$10B, 2015-06~2020-06 5년 350% 이상 104종목(평균 922%) | 80% 진입장벽 · 88% 건전한 재무 · 84% 시총 $2B 미만 · 80%는 주식 수가 늘었다(희석이 있어도 승자) · 인수 활용 | [S] |
| Yartseva 2025 'The Alchemy of Multibagger Stocks' | 미국 2009~2024 10배 464종목 | FCF 수익률·B/M 계수 최대, 출발 평균 시총 $348M·예상 P/E 11배, **이익 성장률은 유의하지 않음**, 모형 설명력 13~16% | 기존 정리 + [S] |
| Mauboussin·Callahan 2026 'Public to Private Equity in the United States' | 미국 상장사 | 2025년 말 상장사 약 3,500개(1996년 정점의 절반), 평균 시총 $20.7B(1976년 $0.8B, 물가 조정) | [S] |

읽는 법(자체추론):
- **승자만 본 표본**이라 확률을 주지 못한다(생존 편향). 기저율은 Chiip 성적표가 앞으로 잰다(5년 3배 6.8%·10배 0.69% — `discovery_engine.md` 4.5).
- 상장사가 줄고 평균 규모가 커졌다 — 작은 성장 기업이 비상장에 오래 머문다. 공개 시장의 10배는 ① 덜 알려진 기존 상장 소형주가 **꺾이는 지점** ② 미국 밖(아시아 비중) ③ 큰 투자 물결의 **공급망 아래 칸**에서 나올 가능성이 높다.
- **2026년 시장 역학** [S, CNBC 2026-06-30 등 보도]: 러셀 2000이 상반기 약 22% 올라 1991년 이후 최고였고, 상위 50종목 중 16개가 반도체 관련(장비·부품·연결)이었다 — AI 설비투자가 공급망 아래로 흘렀다. 다만 이익은 들쭉날쭉하고 금리에 민감하다. 드러켄밀러는 같은 해 초 "AI는 내 투자의 주역이 아니다"라며 구리(공급 부족)를 꼽았다 [S]. 물결의 주도 칸은 바뀐다 — 변화의 방향 관점이 필요한 이유다.
- **2026-11-21 Chiip 자체 계산**: 추적 후보 중 46종목이 기간 고점 대비 50% 넘게 빠져 있다(`playbook.py --drawdowns`). 보유 규율은 지금 당장 쓰이는 규칙이다.

## 3. 판단 체계 — 여섯 관점 교차 점검
| 관점 | 묻는 것 | 스크립트가 주는 숫자 | 통과의 근거 |
|---|---|---|---|
| 성장 여지 | 5년 안에 매출 2배(연 14.9%)가 될 자리, 10년 뒤 | 컨센서스 매출 경로의 연 성장률·2배까지 걸리는 해 | 참조 시장·점유율·신제품(1차 자료) |
| 해자와 자본수익률 | 경쟁우위의 종류, ROIC가 자본비용보다 높고 유지되나 | ROIC(세후 영업이익 ÷ 투하자본) | 해자의 증거와 반증 |
| 재투자 복리 | 번 돈을 높은 수익률로 다시 넣을 곳, 자본 배분 이력 | 재투자율·지속 가능 성장(근사)·소유주 이익 수익률(근사) | 증설·인수 성과·희석 이력 |
| 사람과 문화 | 경영진 지분·기회형 내부자 매수·교체 이력 | (없음 — 서류로) | 위임장·Form 4 |
| 변화의 방향 | 18~24개월 뒤 이익 그림, 유동성 국면 | 2년 뒤 EPS ÷ 다음 12개월 EPS, 금리·신용 스프레드 20일 변화 | 추정 수정·수주·가이던스 |
| 5배 경로 | 이익 성장 × 배수 변화로 5배 이상이 되는 길, 시장이 모르는 이유 | 10배·5배·2배 필요 성장률, 두 엔진 분해 | 배수 사다리·역DCF·합의와의 차이 |

관문(위원회 메모 머리말 `playbook:` — 양식은 `scripts/tenbagger/playbook.py` 맨 위):
- 관점마다 `통과·미달·미확인`과 이유. **통과에는 근거**(1차 출처 URL·서류 이름·저장소 파일)가 있어야 한다. 모르면 미확인 — 미확인은 통과가 아니다.
- focus는 통과 4개 이상, bench는 3개 이상. **해자와 자본수익률이 미달이면 focus 불가.**
- **가장 약한 관점을 스스로 지목**(dissent)하고 이유를 쓴다 — 마스터 가설에도 같은 강도로.
- **보유 규율**: 투자 논리가 살아 있는지 볼 지표 2개 이상. 유지·종료는 가격이 아니라 이 지표와 킬 조건으로 가른다.
- 판단 기간 3~10년을 적는다. 목표 배수(target_multiple)를 함께 적으면 필요한 연 성장률을 계산해 연 45% 이상이면 '희소' 경고를 낸다(사전값 — 5년 6.4배에 해당. Chiip 기저율 5년 3배 6.8%·10배 0.69% 사이).
- **Analysis 리포트**(2026-11-22 마스터 "넣어라"): 같은 구조를 datapack `guru`에 쓰면 본문 '구루 교차 점검' 절과 한 장 요약 한 줄이 된다(`scripts/tenbagger/guru_view.py`). 리포트는 통과 개수를 요구하지 않고 구조만 본다. 통과로 쓴 관점이 계산값과 어긋나면 절에 그대로 싣는다.

산술(잊기 쉬운 숫자): 10배 = 5년 연 58.5% · 7년 38.9% · 10년 25.9% / 5배 = 5년 38.0% · 10년 17.5% / 2배 = 5년 14.9% · 6년 12.2%. 배수가 2배로 재평가되면 10배에 필요한 이익은 5배(5년 연 38%)다.

## 4. 리서치 방법론 — 순서
1. **산술 먼저**: `py scripts/tenbagger/playbook.py <회사 id>` — 필요한 성장률이 합리적 범위인가, 지금 ROIC·재투자율로 그 성장이 나오나.
2. **출발점 확인**: 흑자인가, 싼가(FCF 수익률·EV/EBIT), 작은가, 재무가 버티나(§0-2·4). 출발점이 나쁘면 '회생주' 틀(린치)로 따로 본다.
3. **여섯 관점을 서류로**: 10-K 사업·경쟁·위험 절(해자·성장 여지), 위임장(사람), 현금흐름표·주석(재투자·희석), 어닝콜 Q&A와 추정 수정(변화의 방향), 배수 사다리·역DCF(5배 경로). 섹터 특성은 `sector_lenses/`의 해당 틀로.
4. **반대편 세우기**: 가장 약한 관점 지목, 누가 반대편에서 팔고 있나(메모 other_side), 사전 부검.
5. **보유 규율 적기**: 투자 논리 지표와 킬 조건. 낙폭이 와도 지표가 살아 있으면 유지, 지표가 죽으면 가격과 무관하게 종료.
6. **사후 측정**: 성적표는 91일 중앙값만 보지 않는다 — 1~3년 평균과 오른쪽 꼬리(2배 이상 비율·상위 10% 몫). 월 1회 `--drawdowns` 재심사.

## 5. 하지 않는 것·한계
- 구루의 **집중·비중** 논리(드러켄밀러의 큰 베팅, 베일리 기포드의 상방 크기 비례 비중)는 Chiip 산출물에 비중·금액으로 쓰지 않는다(투자자문 아님). 관점과 질문만 가져온다.
- [M] 표시 인용은 근거로 쓰지 않는다. 베일리 기포드 10문항 원문(Philosophy and process PDF)은 파일 내려받기가 필요해 열지 못했다 — 마스터가 받아 주면 질문 4~10을 대조한다.
- 재투자율·지속 가능 성장·소유주 이익은 **근사**다(운전자본 변화 없음, 유지 설비투자 = 감가상각 가정). 판단의 재료이지 결론이 아니다.
- 승자 표본 연구의 특징을 '확률'로 읽지 않는다. 금지 연결: 스크린 점수 → 경쟁우위, 구루 보유 → 지금도 보유, 낙폭 → 싸다.

## 6. 반증 조건·다음 확인
- 교차 점검을 통과한 메모(통과 4개 이상)의 1년 이상 성과가 미통과 메모보다 낫지 않으면 통과 기준과 관점 구성을 다시 본다(30건 뒤, 표본 외 검정).
- 낙폭 재심사에서 '지표가 살아 있어 유지'한 종목이 이후 1년 시장을 못 이기는 비율이 높으면 재심사 문턱(−50%)과 지표 선택을 고친다.
- 다음 확인: 베일리 기포드 10문항 원문, Mauboussin·Callahan 2025 본문의 최고 종목 낙폭 수치, 버핏 2007 서한 해자 문단.

## 출처
- Baillie Gifford Long Term Global Growth 전략 페이지 — https://www.bailliegifford.com/en/uk/institutional-investor/investment-strategies/long-term-global-growth/
- Berkshire Hathaway 주주서한 1984 — https://www.berkshirehathaway.com/letters/1984.html · 1986 — https://www.berkshirehathaway.com/letters/1986.html
- Mauboussin·Callahan, Drawdowns and Recoveries(2025-05-21) — https://www.morganstanley.com/im/en-us/financial-advisor/insights/consilient-observer/drawdowns-and-recoveries.html
- Bessembinder 2024 요약 — https://marginalrevolution.com/marginalrevolution/2024/09/which-u-s-stocks-generated-the-highest-long-term-returns.html · https://wpcarey.asu.edu/department-finance/faculty-research/do-stocks-outperform-treasury-bills
- Eyesan, Global Outperformers 요약 — https://www.theinvestorspodcast.com/millennial-investing/epic-10bagger-lessons/ · https://ii.co.uk/analysis-commentary/six-secrets-bagging-next-nvidia-ii531702
- Alta Fox, The Makings of a Multibagger 요약 — https://acquirersmultiple.com/2020/11/alta-fox-makings-of-a-multibagger/ · https://behindthebalancesheet.substack.com/p/what-makes-for-a-multi-bagger
- Yartseva 2025 — https://www.open-access.bcu.ac.uk/16180/1/The%20Alchemy%20of%20Multibagger%20Stocks%20-%20Anna%20Yartseva%20-%20CAFE%20Working%20Paper%2033%20(2025).pdf
- Druckenmiller — https://www.morganstanley.com/insights/videos/hard-lessons/duquesne-stan-druckenmiller-iliana-bouzali · https://finance.yahoo.com/news/stanley-druckenmiller-says-d-build-153800006.html
- Ron Baron — https://www.kiplinger.com/investing/mutual-funds/604832/ron-baron-a-fund-legend-shares-stock-picking-secrets · https://www.baroncapitalgroup.com/approach
- Mauboussin·Callahan, Public to Private Equity in the United States — https://www.morganstanley.com/im/en-be/intermediary-investor/insights/consilient-observer/public-to-private-equity-in-the-us-a-long-term-look.html
- 2026 소형주·반도체 — https://www.cnbc.com/2026/06/30/small-cap-stocks-enjoy-best-first-half-since-1991-as-ai-trade-expands.html
