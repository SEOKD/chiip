# 섹터 판단 틀 (마스터 지시 2026-11-13 종목 범위 확대 2단계, ADR-027)

AI 밸류체인 밖 종목은 '병목·해결 기술·고객 채택(샘플→인증→양산)' 틀이 맞지 않는다. 섹터마다 **구조적으로 오르는 이유**를 묻는 질문지를 따로 둔다.
섹터 순환 스크린(`scripts/discovery/sector_rotation.py`) 상위 후보를 볼 때, 이 틀로 판단 카드를 쓴다.

| 틀 | 파일 | 쓰는 섹터(config/sector_map.yaml) |
|---|---|---|
| 헬스케어 | `health.md` | health·biotech·medtech |
| 금융 | `financials.md` | financials·regional_banks·real_estate |
| 산업재 | `industrials.md` | industrials·infra_build·airlines·shipping·robotics·life_tools(계측·연구 장비) |
| 소비재 | `consumer.md` (+ 기존 `knowledge/methods/consumer_lens.md`) | cons_disc·cons_staples·retail·homebuild·media_ent·luxury |
| 에너지·소재 | `energy.md` | energy·utilities·materials·chemicals·gold·copper·solar |
| 소프트웨어 | `software.md` | software·cyber·comm |
방위·원자력·우주는 기존 `config/defense.yaml`·`knowledge/methods/nuclear_space_lens.md`를 쓴다.

## 판단 카드 — `knowledge/models/discovery/lens_cards/<id>.yaml`
```yaml
id: us-xyz            # 발굴 id(us-<티커>)
ticker: XYZ
lens: health          # 위 틀 이름
as_of: 2026-11-13
answers:              # 틀의 번호 질문마다 한 줄 — 모르면 '미확인'(빈칸을 그럴듯하게 채우지 않는다)
  1: "..."
edge: 6.5             # 0~10, 아래 기준
evidence: [https://...]   # 1차 출처 URL 하나 이상(10-K·보도자료·규제 문서)
kill: "무엇이 나오면 틀렸나 — 지표·문턱·날짜"
why: "한 줄 요지"
```
`py scripts/discovery/sector_rotation.py --card-check <파일>` 통과분만 edge가 발굴 선별 점수에 들어간다(90일 유효). 통과하지 않으면 edge 미판정 5 → '① 아이디어'에 머문다.

## edge 기준(모든 틀 공통)
- **8~10**: 구조적 우위가 숫자로 확인되고(2개 이상 지표가 동종보다 확연히 낫다), 우위가 3년 이상 이어질 이유(규제·네트워크·전환 비용·원가)가 1차 출처로 있다
- **6~7.9**: 우위 지표 1개 이상 확인, 지속 이유가 있으나 일부 미확인
- **4~5.9**: 성장은 있으나 우위가 업황·일회성으로 설명된다, 또는 핵심 질문 절반 이상 미확인
- **0~3.9**: 우위 근거 없음, 또는 반증 사실(점유율 하락·규제 악재·희석)이 이미 있다

## 공통 금지 연결(CLAUDE.md 금지표)
스크린 점수 → 경쟁우위 / 섹터 성장 → 기업 이익 / 매출 급증 → 이익 증가 / 승인·계약 발표 → 매출 확정 / 주가 급등 → 펀더멘털 변화.
엣지 원천은 Chiip 공정 해석이 아니라 '속도·정량'으로 표시한다. 표시할 수 없으면 카드를 쓰지 않는다.
