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
