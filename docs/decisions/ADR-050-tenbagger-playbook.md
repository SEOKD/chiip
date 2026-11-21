# ADR-050 텐배거 판단 체계 — 구루 교차 점검·보유 규율·오른쪽 꼬리 성적표

- 날짜: 2026-11-21
- 상태: 채택(사전값, 피팅 대기)
- 지시: 마스터 "Ten-bagger 종목을 발굴할 수 있는 사고 논리와 판단 체계, 리서치 방법론에 대해 최신 기법을 조사하고 이를 시스템 기반에 업데이트할 수 있도록 하라. 스탠리 드러켄밀러, 베일리 기포드, 론 바론, 피터 린치, 워렌 버핏 등 글로벌 구루의 투자 논리를 학습하고 2026년 또는 2020년대 최근 시장 역학과 투자 성공 방정식도 참조하라."
- 방법론·출처: `knowledge/methods/tenbagger_playbook.md`(출처 등급 [V] 1차 확인 · [S] 2차 요약 · [M] 기억 미검증)

## 진단 — 기존 체계에 없던 것
1. 위원회 메모(`scripts/discovery/memo_check.py`)는 12개월 틀이다 — 상방÷하방 2.0, 365일 안 촉매. 5~10년 복리 경로를 묻는 관문이 없었다. 10배는 속도가 아니라 기간에서 나온다(최고 누적 수익 17종목 연 복리 평균 13.47% — Bessembinder 2024, 2차 요약).
2. 자본수익률 × 재투자 여지(버핏)와 5년 매출 2배 시험(베일리 기포드)이 렌즈 문장으로만 있고 숫자·관문이 없었다.
3. 18~24개월 뒤 이익 그림과 유동성 국면(드러켄밀러)을 보는 관점이 없었다.
4. 채널 성적표가 91일 초과수익 **중앙값**으로 채널을 평가했다 — 소수 종목이 수익을 만드는 텐배거형 채널에 불리하다.
5. 가격 낙폭과 투자 논리 훼손을 가르는 보유 규율이 없었다. 2026-11-21 기준 추적 후보 46종목이 기간 고점 대비 50% 넘게 빠져 있다(`playbook.py --drawdowns`).

## 결정
- **여섯 관점 구루 교차 점검** — `config/tenbagger_playbook.yaml` views: 성장 여지(베일리 기포드) · 해자와 자본수익률(버핏) · 재투자 복리(버핏·바론) · 사람과 문화(바론·베일리 기포드·린치) · 변화의 방향(드러켄밀러) · 5배 경로와 시장이 모르는 이유(베일리 기포드·린치).
  관점마다 통과·미달·미확인 + 이유. 통과에는 근거(1차 출처 URL·서류 이름·저장소 파일)가 있어야 한다. 미확인은 통과가 아니다.
- **계산은 스크립트** — `scripts/tenbagger/playbook.py`: 10배·5배·2배 필요 성장률, 컨센서스 매출 경로의 5년 2배 시험, ROIC·재투자율·지속 가능 성장(근사), 소유주 이익 수익률(근사), 2년 뒤 EPS ÷ 다음 12개월 EPS, 유동성 국면(10년물·하이일드 스프레드 20일 변화), 고점 대비 낙폭. 칸이 없으면 None(미확인).
- **관문** — `memo_check.check`가 `playbook.check`를 부른다. 메모 날짜 2026-11-22부터(또는 `playbook:` 칸이 있으면) 적용: focus 통과 4개 이상·해자와 자본수익률 미달이면 불가, bench 3개 이상, 가장 약한 관점 지목(dissent), 투자 논리 지표 2개 이상(hold.kpis), 판단 기간 3~10년. 목표 배수를 적으면 필요한 연 성장률이 45% 이상일 때 '희소' 경고. 이전 메모는 그대로 통과한다.
- **보유 규율** — `playbook.py --drawdowns`: 추적 후보가 고점 대비 50% 이상 빠지면 **재심사** 목록에 올린다. 제외가 아니다 — 킬 조건과 투자 논리 지표를 다시 확인해 지표가 살아 있으면 유지한다(미국 6,500종목 중앙 낙폭 85%, 최고 종목도 큰 낙폭 — Mauboussin·Callahan 2025). 월 1회 watch.csv 점검 회차에 돌린다.
- **성적표** — `scripts/discovery/leads.py`: 평가 기간에 730·1095일 추가, `tail()`로 90분위 초과·2배 이상 비율·상위 10% 몫을 기간마다 계산하고 '오른쪽 꼬리(1년 이상)' 절을 낸다. 가중·문턱은 바꾸지 않는다(판정은 Model Lab 표본 외 검정).
- **연결** — 카드 양식(`knowledge/models/tenbagger/cards/_template.md` 머리말 playbook 칸·'구루 교차 점검'·'보유 규율' 절), 스킬 `tenbagger-card`, 지시서 `docs/tasks/chiip-tenbagger.md`(0-B d·e, 2, 4), `docs/channels/discovery.md`, 렌즈 `sector_lenses/multibagger.md`, `discovery_engine.md` 7절.

## 등록부에 올릴 상수 (prm-pb-* — 모두 사전값, status prior)
`knowledge/models/params/registry.yaml`에 다른 세션의 미커밋 변경이 있어 이 커밋에서는 손대지 않았다. 아래 표대로 등록한다(model `tenbagger.playbook`).
| id | binding | 값 | 근거(사전값) | 피팅 목표 |
|---|---|---|---|---|
| prm-pb-pass-min-focus | config/tenbagger_playbook.yaml#gate.pass_min.focus | 4 | 여섯 관점의 3분의 2 — Chiip 가정(미검증) | 통과 수별 1년 이상 초과수익(30건 뒤) |
| prm-pb-pass-min-bench | config/tenbagger_playbook.yaml#gate.pass_min.bench | 3 | 여섯 관점의 절반 — Chiip 가정(미검증) | 같음 |
| prm-pb-kpis-min | config/tenbagger_playbook.yaml#gate.kpis_min | 2 | 지표 하나는 우연에 흔들린다 — Chiip 가정(미검증) | 재심사 '유지' 판단의 사후 적중 |
| prm-pb-double-5y | config/tenbagger_playbook.yaml#arithmetic.double_5y | 0.1487 | 5년 2배 산술(2^(1/5) − 1) — 베일리 기포드 LTGG 질문 1(2차 발췌) | 고정(산술) |
| prm-pb-rare-cagr | config/tenbagger_playbook.yaml#arithmetic.rare_cagr | 0.45 | 5년 6.4배 — Chiip 조사 G 기저율(5년 3배 6.8%·10배 0.69%) 사이 | 메모 목표 경로의 사후 도달 비율 |
| prm-pb-drawdown-review | config/tenbagger_playbook.yaml#arithmetic.drawdown_review | 0.50 | 중앙 낙폭 85%·최고 종목도 큰 낙폭(Mauboussin·Callahan 2025) — 문턱은 Chiip 가정 | 재심사 뒤 1년 초과수익 |
| prm-pb-liq-tighten-10y | config/tenbagger_playbook.yaml#liquidity.tighten.us10y_d20_bp | 25 | 드러켄밀러 유동성 관점의 대용 지표 — Chiip 가정(미검증) | 국면별 후보 초과수익 |
| prm-pb-liq-tighten-hy | config/tenbagger_playbook.yaml#liquidity.tighten.hy_d20_bp | 40 | 같음 | 같음 |
| prm-pb-liq-ease-10y | config/tenbagger_playbook.yaml#liquidity.ease.us10y_d20_bp | -25 | 같음 | 같음 |
| prm-pb-liq-ease-hy | config/tenbagger_playbook.yaml#liquidity.ease.hy_d20_bp | -30 | 같음 | 같음 |

## 하지 않은 것
- 구루의 집중·비중 논리(큰 베팅, 상방 크기 비례 비중)는 넣지 않았다 — 비중·금액 지시가 된다(CLAUDE.md). 관점과 질문만 가져왔다.
- 알파 점수(score.py)·발송 관문은 바꾸지 않았다. 교차 점검은 위원회 메모·카드 단계의 관문이다.
- 유동성 국면은 표시만 한다 — 국면으로 종목 판정을 자동으로 바꾸지 않는다.
- [M] 표시 인용(베일리 기포드 질문 4~10 문구, 버핏 2007 서한 해자 문단, 드러켄밀러 유동성 발언)은 근거로 쓰지 않았다. 원문 대조 뒤 등급을 올린다.

## 반증·다음 확인
- 교차 점검 통과 메모의 1년 이상 초과수익이 미통과(보류) 메모보다 낫지 않으면 통과 기준과 관점 구성을 다시 본다(30건 뒤, 표본 외 검정 — scripts/fit/stepwise.py).
- 재심사에서 '지표가 살아 있어 유지'한 종목이 이후 1년 시장을 못 이기는 비율이 절반을 넘으면 문턱(−50%)과 지표 선택을 고친다.
- 재투자율·소유주 이익 근사(유지 설비투자 = 감가상각, 운전자본 변화 없음)가 실제 서류 값과 크게 다르면 계산식을 바꾼다.
- 다음 확인: 베일리 기포드 'Philosophy and process' 원문(파일 내려받기 필요 — 마스터 몫), Mauboussin·Callahan 2025 본문의 최고 종목 낙폭 수치, 버핏 2007 서한.

## 2026-11-22 추가 — Analysis 리포트 절 (마스터 "넣어라")
- `scripts/tenbagger/guru_view.py`: 한 장 요약 '구루 여섯 관점으로 보면 어떤가?'(피터 린치 줄 다음)와 본문 '구루 교차 점검' 절(피터 린치 분류 다음). 관점마다 설명 박스(질문·이유·계산한 숫자·근거, 판정 꼬리표) + 배수별 필요 성장률 표 + 보유 규율 + 한계 문장.
- 재료는 datapack `guru` — 메모·카드의 playbook 칸과 같은 구조다. datapack `playbook`은 2026-11-16부터 투자 포인트·모멘텀·가격 틀(playbook_view.py)이 쓰고 있어 이름을 따로 뒀다.
- 리포트는 통과 개수를 요구하지 않는다(`playbook.check(…, "report")` — 구조만). 나쁜 회사도 리포트는 쓰기 때문이다. 2026-11-23 리포트부터 `guru`가 없으면 조립이 멈춘다(당일 진행 중인 회차를 막지 않게 하루 뒤부터). 그 전 리포트는 숫자만 싣고 판정은 미확인.
- 숫자와 판정의 어긋남(통과인데 5년 2배 미달 · ROIC < 자본비용 · 2년 뒤 EPS 감소)은 조립 때 경고로 찍고 절에도 싣는다 — 마스터 가설도 같은 강도로 반대 검증.
- 설비투자가 감가상각 이하인 회사는 '설비 재투자율 0%(연구개발·인수 재투자는 이 숫자에 없다)'로 쓰고 지속 가능 성장은 내지 않는다(BESI ROIC 71.6%·재투자율 0%가 '성장 불가'로 읽혔다).
- 근거로 치는 서류 이름을 넓혔다(실적 발표·위임장·반기보고서·어닝콜·결산 자료 등 한글 통칭). URL은 출처 목록으로 보내고 표에는 싣지 않는다.
- 정정: 필요 성장률을 네 자리로 줄였다가 다시 반올림해 7년 10배가 39.0%로 찍혔다. 맞는 값은 38.9%다 — 여섯 자리로 두고 표시할 때 한 번만 반올림한다(방법론 문서도 고쳤다).
- 함께 고친 것: 설명 박스 꼬리표(`.bx .tag`)가 2026-11-20 추가된 판단 이름표 스타일(`.tag`)과 겹쳐 글자색과 배경색이 같아졌다(모든 리포트의 박스 꼬리표 30개가 안 읽혔다). 배경을 없애 원래대로 돌렸다.
- 확인: BESI 2026-11-21 리포트 사본으로 조립·렌더(저장소 리포트는 건드리지 않음) — 절 순서, 용어 풀이 점검 통과, 날짜 관문, 재료 없는 옛 리포트의 숫자만 표시.
