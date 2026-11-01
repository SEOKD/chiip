# ADR-014 데이터 우선순위: Fiscal.ai 1순위, Zacks·Easyconomics 2순위

- 날짜: 2026-11-01 · 결정: 마스터 지시 · 상태: 채택
- 지시: "데이터 추출 우선순위는 Fiscal.ai를 1순위, Easyconomics와 Zacks를 2순위로 정하라. Eayconomics도 호출 제한이 있으니 같은 우선순위인 Zacks와 번갈아가면서 쓰도록 해라. 2순위 채널끼리 서로 보완할 부분이 있으면 보완하는 구조도 만들어라."

## 배경
최근 12개 리포트의 서프라이즈 추정 119행 중 Zacks가 79행이었다. 호출 상한 때문이 아니다(최근 4일 964회에서 상한 오류 0건). company_estimates가 지난 분기의 발표 전 추정을 남기지 않아 코드가 2순위로 내려간 것이다.

## 결정
1. ADR-012의 'easyconomics 호출 금지'를 푼다. Fiscal.ai 칸이 빌 때만 2순위를 부른다.
2. 항목별 경로는 `config/data_sources.yaml`이 정본이다. 호출 순서는 `scripts/fiscal/source_router.py`가 정한다. 두 채널이 모두 내는 항목은 번갈아 쓰고, Easyconomics가 하루 상한이나 제한 응답에 걸리면 뒤로 보낸다.
3. Zacks는 Fiscal.ai MCP 안의 데이터이므로 호출 수를 세지 않는다.
4. Fiscal.ai 발표 전 추정을 매일 저장한다(`scripts/fiscal/estimates.py`, `knowledge/models/estimates/snapshots.csv`). 순서는 저장한 Fiscal 값 → 차례인 2순위 → 다른 2순위다.
5. 보완값은 실적 대조를 통과할 때만 쓴다. 이익률은 같은 제공처 짝으로만 나누므로 매출을 보완해도 원래 Zacks 짝을 `pair`에 남긴다.

## 대가·제약
- Easyconomics 실제 호출 한도는 미확인이다. `limits.easyconomics.daily_cap`은 보수적 값이다.
- Easyconomics `company_profile`의 추정·목표가는 출처 표시가 yfinance다. Zacks와 정의가 다를 수 있어 10% 넘는 차이는 출력에 표시한다.
- 지난 분기 저장값은 복구할 수 없다. 효과는 다음 분기 발표부터 나온다.
- 예약 작업의 앱 권한에 Easyconomics 도구가 허용돼 있는지는 첫 실행에서 확인해야 한다.

## 개정 2026-11-01 — Chiip Analysis 2순위 세 채널
- 지시: "Chiip Analysis에서 데이터 가져오기 1순위는 Fiscal.ai, 2순위는 Easyconomics, Zacks, yfinance다. 2순위에서 한 가지 방법만 쓰지 말고 세 가지 방법을 모두 써라. 2순위 세 가지 방법 모두 균형 있게 사용하라."
- 결정: 리포트마다 세 채널을 모두 호출하고, 누적 사용량이 적은 채널부터 빈칸을 채운다. 번갈아 쓰기를 사용량 균형으로 바꾼다.
- 제약: yfinance는 Easyconomics MCP가 내주는 출처 자료만 쓴다. 직접 호출은 Yahoo robots.txt 금지이고 브라우저 위장 라이브러리를 거쳐 차단을 넘는 일이라 하지 않는다. 호출 수는 Easyconomics 상한에 묶인다.
- 한계: Easyconomics 두 경로의 추정이 거의 같아 실질 원출처는 둘일 수 있다. 균형은 경로 기준이지 독립성 기준이 아니다.

## 개정 2026-11-01 — 컨센서스 채널 확장
- 지시: "Chiip Proviser에 기업 재무 컨센서스 데이터를 가져오는 채널을 확장하는 방안을 작동할 때마다 고민하라. 다른 데이터 파이프라인도 확보해라. Investing.com와 CNBC 등 아티클에 인용된 VisibleAlpha, LSEG, FactSet 컨센서스를 가져와라."
- 결정: Proviser 6-5 단계와 기사 인용 장부(`scripts/fiscal/cited.py`)를 둔다. 인용값은 출처 없이 저장하지 않고, 재인용은 origin_id로 묶으며, 제공사별 값은 평균 내지 않는다. est. 순위에는 넣지 않는다(`use_in_est: false`, 마스터 결정 대기).
- 제약: CNBC robots.txt는 Claude 계열 수집기를 금지하고 Reuters·MarketWatch·Barron's는 전체 금지다. 직접 열지 않으므로 수집량은 검색 결과에 보이는 값으로 제한된다. CNBC가 Claude-SearchBot도 막아 인용값이 적을 수 있다.
