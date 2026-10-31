# Chiip Portfolio 운영 규칙

> CLAUDE.md '출력 채널'에서 옮긴 마스터 지시(2026-10-31, AAP-20261031-02). 새 지시도 여기에 적는다.

- **Chiip Portfolio**(2026-10-29 마스터 지시): 마스터 보유 종목(`config/portfolio.yaml`, 바뀌면 마스터가 알려줌)의 공시·실적·어닝콜·IB 커버리지·커뮤니티 관심도(ApeWisdom 레딧 언급·위키 조회)·일정을 팔로업. 데일리에 시장·섹터 국면(2026-10-30 — 지수·금리·변동성·신용 FRED, 섹터 센티멘트·펀더멘털 사분면, 매크로·마이크로 요인을 따로, 금리 민감도, `radar/market_regime.py`, `config/market_watch.yaml`)과 오버행 장부(`radar/overhang.py`). 관문 `radar/portfolio.py`가 새 자료를 내놓을 때만 모델 판단(매시 35분), 화~토 아침 데일리 1통. invest 모드 — 사실·지표·일정만, 매매·비중 지시 금지.
- **종합 9.5 연구 명단**(2026-10-31 마스터 지시, `scripts/discovery/composite.py`, `config/composite.yaml`): 텐배거 레이더 밖 종목까지 알파 30%·손익비 30%·기술적 20%·시의성 20%로 10점 평가해 9.5 이상만 Portfolio 데일리에 싣는다. 없으면 싣지 않는다. 지표·연구 후보이지 추천이 아니다 — 마스터 포지션을 읽지 않고 비중·시점·금액을 내지 않는다.
