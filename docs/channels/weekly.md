# Chiip Weekly Review 운영 규칙

> CLAUDE.md '출력 채널'에서 옮긴 마스터 지시(2026-10-31, AAP-20261031-02). 새 지시도 여기에 적는다.

- **Chiip Weekly Review**(2026-10-31 재설계 — 마스터 평가 3/10 이하): 결론 → 글로벌 지수 → 주간 상승률(US 20, US(<$10B)·Europe·Japan·Korea·Taiwan·Hong Kong 각 10, Dean's Ticker 양식) → 상승 업종 → 이번 주 바뀐 것 3~4건(무엇이·왜·유리·불리·다음 확인) → 섹터 온도 → 다음 주 볼 것 → 틀릴 조건. Fiscal.ai 데이터를 쓰고, 판정할 수 없는 항목은 빼고, 본론만 쓰며 작업 과정은 쓰지 않는다. 렌더러·관문 `scripts/weekly/render.py`·`config/weekly_review.yaml`, 운영 기록은 `outputs/brief/<주차>_ops.md`. **발행은 Artifact → 노션 → 텔레그램 한 묶음**(2026-10-31 마스터 지시 "Weekly Report를 작성한 뒤 텔레그램 봇에 공유할 때 Notion의 Weekly 페이지에도 올리도록", `scripts/weekly/publish_weekly.py`): 다시 쓰면 노션은 같은 페이지 갱신, 텔레그램은 '수정판'으로 보낸다.

**무역·PPI(마스터 지시 2026-11-02):** '이번 주 바뀐 것'과 '다음 주 볼 것'에서 그 주에 새로 나온 무역·PPI 수치가 판단을 바꿀 때 쓴다. 필요할 때 `py radar/trade_ppi.py --status`(또는 `--need <회사 id>`)로 7개 지역 세부 지표를 본다. PPI 전년비·수입처 변화가 판단을 바꿀 때만 쓰고, 나열하지 않는다. 별표는 업종 대용 지수다. 값이 없으면 '미확인'이다.
- **AI 하드웨어 리드타임·병목**(2026-11-04 마스터 지시, 다음 Weekly부터): 주간 실적·콜·리포트의 부품별 리드타임으로 압박도(지금÷평시)·가중 병목 지수·병목 이동을 낸다. JSON `leadtime`, 엔진 `scripts/weekly/render.py` leadtime_model, 관문은 부품 4~12개.
