---
cand_id: TB-YYYYMMDD-NN
company: 
ticker: 
region: 
path: bottleneck | quant
added_on: 
status: 관찰 | 추적 | 종료
value_source: [해석, 정량]      # 부가가치 원천(독점·해석·속도·정량)
playbook:                       # 구루 교차 점검(config/tenbagger_playbook.yaml) — py scripts/tenbagger/playbook.py --check <이 파일>
  horizon_years: 7              # 판단 기간 3~10년
  target_multiple: 5            # (선택) 이 기간에 기대하는 배수 — 필요한 연 성장률이 45% 이상이면 '희소' 경고
  views:                        # verdict: pass(통과)·fail(미달)·unknown(미확인) — 통과에는 근거(1차 출처 URL·서류 이름·저장소 파일)
    runway:       {verdict: unknown, why: "", evidence: ""}   # 성장 여지 — 5년 매출 2배 자리
    moat_returns: {verdict: unknown, why: "", evidence: ""}   # 해자와 자본수익률
    reinvestment: {verdict: unknown, why: "", evidence: ""}   # 재투자 복리 — 자본 배분·희석
    people:       {verdict: unknown, why: "", evidence: ""}   # 사람과 문화
    change:       {verdict: unknown, why: "", evidence: ""}   # 변화의 방향 — 18~24개월 뒤 이익, 유동성 국면
    mispricing:   {verdict: unknown, why: "", evidence: ""}   # 5배 경로와 시장이 모르는 이유
  dissent: {view: , why: ""}    # 가장 약한 관점과 이유
  hold: {kpis: [], rule: ""}    # 보유 규율 — 투자 논리 지표 2개 이상
---
[모드: invest / 범위: 텐배거 후보 / 기준시각: ]

## 결론 (1문장)
## 병목 투자 논리 — 어떤 병목을, 어떤 기술로, 왜 이 회사가
## 10배 경로 (숫자)
| 항목 | 현재 | 5년 뒤 (기본) | 근거 id |
|---|---|---|---|
| TAM | | | |
| 점유율 | | | |
| 매출 | | | |
| 영업이익률 | | | |
| 순이익 | | | |
| 출구 배수(P/E) | | | prm-… |
| 내포 시가총액 | | | |
- 현재 시가총액 대비 배수: ○배 / 10배에 필요한 가정: … / 그 가정의 확률(판단): ○%
## 가격 내포 기대 — 지금 주가가 이미 가정하는 성장
## 정량 요인 점수 (config/tenbagger.yaml factors)
## 구루 교차 점검 — 여섯 관점 (숫자는 `py scripts/tenbagger/playbook.py <회사 id>`부터, 방법론 knowledge/methods/tenbagger_playbook.md)
| 관점 | 판정(통과·미달·미확인) | 이유 | 근거(1차 출처) |
|---|---|---|---|
| 성장 여지 — 5년 안에 매출 2배가 될 자리 | | | |
| 해자와 자본수익률 — ROIC와 지속 | | | |
| 재투자 복리 — 자본 배분·희석 이력 | | | |
| 사람과 문화 — 경영진 지분·내부자 매수 | | | |
| 변화의 방향 — 18~24개월 뒤 이익, 유동성 국면 | | | |
| 5배 경로 — 이익 성장 × 배수, 시장이 모르는 이유 | | | |
- 가장 약한 관점과 이유: 
## 보유 규율 — 가격이 아니라 지표로 유지·종료를 가른다
- 투자 논리 지표(2개 이상): 
- 고점 대비 −50%면 재심사 — 지표가 살아 있으면 유지, 지표가 죽으면 가격과 무관하게 종료
## 반대 검증 — 가장 약한 고리, 대안 설명, 금지표
## 킬 조건 (하나라도 충족 시 종료)
## 다음 확인 사건·카탈리스트
## 종료 상태: 판단 가능 / 조건부 판단 / 핵심 근거 부족

공개 자료 기반 분석이며 투자 권유가 아님
