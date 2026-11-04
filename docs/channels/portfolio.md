# Chiip Portfolio 운영 규칙

> CLAUDE.md '출력 채널'에서 옮긴 마스터 지시(2026-10-31, AAP-20261031-02). 새 지시도 여기에 적는다.

- **Chiip Portfolio**(2026-10-29 마스터 지시): 마스터 보유 종목(`config/portfolio.yaml`, 바뀌면 마스터가 알려줌)의 공시·실적·어닝콜·IB 커버리지·커뮤니티 관심도(ApeWisdom 레딧 언급·위키 조회)·일정을 팔로업. 데일리에 시장·섹터 국면(2026-10-30 — 지수·금리·변동성·신용 FRED, 섹터 센티멘트·펀더멘털 사분면, 매크로·마이크로 요인을 따로, 금리 민감도, `radar/market_regime.py`, `config/market_watch.yaml`)과 오버행 장부(`radar/overhang.py`). 관문 `radar/portfolio.py`가 새 자료를 내놓을 때만 모델 판단(주중 01·07·13·19시 35분, 주말 07시 35분, 2026-11-01 마스터 지시), 화~토 아침 데일리 1통. invest 모드 — 사실·지표·일정만, 매매·비중 지시 금지.
- **Buy Call**(2026-11-02 마스터 지시 "Portfolio Buy Call 구조 수정해", `scripts/discovery/buy_call.py`, `config/composite.yaml` buy_call): 최신 리포트의 규칙 계산 등급을 현재가로 다시 재서 Buy 이상이고 알파 6.0 이상이며 리포트가 45일 안이면 Portfolio 데일리 `■ Buy Call` 절에 싣는다. 진입은 🆕, 빠지면 `해제`와 이유를 쓴다. 기록 `knowledge/models/portfolio/buy_call_log.csv`. 등급은 모델이 바꾸지 않는다. 구매 등급·목표주가는 전하되 매매·비중·금액 지시와 마스터 포지션 읽기는 금지다.
- **종합 9.5 연구 명단**(2026-10-31 마스터 지시, `scripts/discovery/composite.py`, `config/composite.yaml`): 텐배거 레이더 밖 종목까지 알파 30%·손익비 30%·기술적 20%·시의성 20%로 10점 평가해 9.5 이상만 Portfolio 데일리에 싣는다. 없으면 싣지 않는다. 지표·연구 후보이지 추천이 아니다 — 마스터 포지션을 읽지 않고 비중·시점·금액을 내지 않는다.

- **와치리스트 자동 편입·제외**(2026-11-04 마스터 지시): `scripts/portfolio/watchlist.py`가 알파·종합 점수(분위)·Buy Call로 관심 종목을 넣고 뺀다(규칙 `config/watchlist.yaml`, 등록부 prm-watchlist-*, 기록 `knowledge/models/portfolio/watchlist_log.csv`). 보유는 마스터 몫. 제외는 지우지 않고 status: 종료.
