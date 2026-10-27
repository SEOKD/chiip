# 데이터 스키마 요약

상세 정의는 `docs/BUILD_PROMPT.md` §5·§11.12·§12.6·§13.7~13.8. 빈 양식은 `docs/templates/`. 이 문서는 **ID 규칙과 허용값**을 한곳에 모은 것이며 `scripts/validate_claims.py`가 같은 값을 쓴다.

## ID 규칙
| 대상 | 형식 | 예 |
|---|---|---|
| 기업 엔티티 | `co-<영문 소문자>` | `co-skhynix` |
| 제품 | `pr-<영문>` | `pr-hbm4-12h` |
| 팹·거점 | `fab-<회사>-<사이트>` / `us-<회사>-<도시>` | `us-samsung-taylor` |
| 학회 | `cf-<약칭>-<연도>` | `cf-iedm-2026` |
| 주장 | `C-YYYYMMDD-NNN` | `C-20261027-014` |
| 원천 문서 | `S-YYYYMMDD-NNN` | `S-20261023-003` |
| 영향 카드 | `R-YYYYMMDD-HHMM-NNN` | `R-20261027-1543-005` |
| 이벤트 클러스터 | `EV-YYYYMMDD-NNN` | |
| 역방향 신호 | `SIG-YYYYMMDD-NNNN` | |
| 페어 | `pair-<a>-<b>-<제품>` | `pair-skhynix-tsmc-hbm4-basedie` |
| 테제 | `th-<slug>` | |
| 인물 | `pe-<slug>` | |
| 회귀 사례 | `E-NNN` | `E-001` |
| 원천 등록부 | `src-<이름>` | `src-dart` |

파일 경로: 주장 `knowledge/claims/YYYY/MM/<id>.yaml`, 카드 `radar/cards/YYYY/MM/<id>.yaml`, 신호 `radar/reverse/signals/YYYY/MM/<id>.yaml`.

## 주장(claim) 허용값
| 필드 | 허용값 |
|---|---|
| `claim_type` | 확정사실 · 가이던스 · 추정 · 채널체크 · 자체추론 · 필드인텔 |
| `speaker_type` | 기업 · 정부 · 표준기관 · 연구자 · IB · 언론 · 사용자취재 · AI |
| `novelty` | 신규 · 수정 · 추가검증 · 반복 · 재해석 · 미확정 |
| `subject.role` | 설계 · IP · 제조 · 조립 · 검사 · 판매 · 운영 · 구매 |
| `status.manufacturing` | 개발 · 파일럿 · 장비설치 · 공정안정화 · 생산확대 · 출하 · null |
| `status.customer` | 샘플 · 평가 · 인증완료 · 디자인윈 · 계약 · 고객제품적용 · null |
| `status.business` | 투자계획 · 승인·자금 · 건설 · 가동 · 매출인식 · 현금회수 · null |
| `supply_relation` | 확정공급 · 과거공급 · 인증·평가 · 후보 · 분석상추정 · 미확인 · 해당없음 |
| `confidence` | 높음 · 중간 · 낮음 |
| `financial_link` | 물량 · 함량 · 가격 · 점유율 · 제조비용 · 시점 · 해당없음 |

필수: `id, created, subject.company, statement, claim_type, speaker_type, novelty, evidence[≥1](source_id, locator, gist_ko), public_corroborated, confidence, falsifier, next_check, user_confirmed`.

검증 규칙(요지):
- `claim_type: 필드인텔`이면 `field_intel_ref`는 F1 출처이거나 `field_intel_index`의 추상 id(`FI-…`)여야 한다. 원문·인명 금지.
- `public_corroborated: false` 주장은 invest·public 출력에 쓰지 않는다.
- `status`의 세 축은 서로 다른 근거로만 채운다.

## 공통 형식
- 시각: KST ISO 8601(`2026-10-27T15:43+09:00`). 해외 원천은 원 시간대 병기.
- 날짜만: `YYYY-MM-DD`. 기간: `2026H2`, `2026Q3`, `FY2026`.
- 단위 규칙: BUILD_PROMPT §5.7. `scripts/check_units.py`가 흔한 혼동을 경고한다.

## 신호 강도 (역방향 레이더)
S0 노이즈 · S1 루머 · S2 정황 · S3 준공식 · S4 공식(상대방) · S5 확정(양측). S3 이상만 claim-intake.

## 정책 단계 (미국 정부)
입법: 발의 → 위원회 → 본회의 통과 → 양원 통과 → 서명 → 시행
행정 규칙: 조사 개시 → 규칙안 → 의견 수렴 → 최종 규칙 → 시행일 → 유예·예외
보조금: 발표 → 예비 합의 → 최종 계약 → 단계별 지급 → 조건 변경·회수
인허가: 신청 → 보완 → 공청회 → 승인 → 착공
지방 인센티브: 안건 상정 → 의결 → 협약 체결 → 이행 점검
