---
name: mirror-trade
description: 역방향 L3 v2: 일본 재무성·네덜란드/Eurostat·UN Comtrade·미국 수입 통계로 반도체 장비·소재의 대한국 수출(또는 한국산 대미 수입)을 추적해 국내 팹 장비 반입·출하의 거울로 쓴다. 원천별 키·접근 방법은 처음 실행 때 공식 문서로 확인.
argument-hint: "[HS 코드 또는 품목]"
---

# mirror-trade — 거울 무역 데이터 (§11.4 L3, §11.5)
1. 품목: 반도체 제조장비(노광·증착·식각 등) HS 코드, 기판·소재 HS 코드 — **코드는 공식 HS 표로 확인 후** `config/mirror_matrix.yaml`의 `trade_codes`에 기록.
2. 원천(처음 실행 때 공식 문서로 엔드포인트·키·약관 확인, 결과를 이 파일에 기록):
   - 일본 재무성 무역통계 / e-Stat API(앱 ID 필요)
   - Eurostat Comext(네덜란드 → 한국)
   - UN Comtrade(키 필요할 수 있음)
   - 미국 인구조사국 무역 API·USITC DataWeb(한국산 메모리·반도체 대미 수입)
3. 월별 대한국 수출액·수량을 `knowledge/models/mirror_trade.csv`에 누적: `period,reporter,partner,hs,value,unit,qty,source`.
4. 급증·급감은 S2 정황 신호(장비 반입 시점 추정 — 가설), 국내 인허가·장비 반입 보도와 대조.
