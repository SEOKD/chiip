# ADR-017 리포트 제품 이미지·BOM 분해도 (Gemini 이미지 API)

- 날짜: 2026-11-08
- 마스터 지시: 「Chiip 구현 지시서 — 리포트 제품 이미지·BOM 분해도」 v1.2, 「산업 리포트의 제품·분해도 이미지」 v1.1 — "이대로 구현하라"
- 상태: **구현(2026-11-08)** — 실제 생성은 구글 선불 크레딧이 0이라 402로 멈춰 있다(아래 §5)

## 1. 왜 그림은 Gemini, 이름표·BOM은 Chiip인가
- 이미지 모델은 글자·숫자·부품 이름을 틀리게 그리고, 그린 내용에 출처가 없다. CLAUDE.md "확인 안 된 단정 금지"를 그림에도 적용한다.
- 그래서 Gemini에는 **글자 없는 개념도**만 그리게 하고, 부품 번호·이름·공급사·출처는 Chiip이 BOM 사실로 SVG 이름표와 표를 얹는다.
- 출처 없는 부품('추정')은 분해도 이름표에 올리지 않고 BOM 표에만 회색으로 둔다. '확인' 부품이 6개 미만이면 분해도를 그리지 않고 BOM 표만 싣는다(구성을 보는 것이 목적).
- 모든 이미지에 고정 캡션 "AI 생성 개념도 · 실제 제품·내부 구조·비율과 다를 수 있음". 로고·상표·글자·숫자·실존 인물·사진 같은 연출·특정 회사 실물 복제를 그리지 않는다.

## 2. 비용 — 두 겹
- 구글 예산 한도 ₩13,000/월(마스터 설정, Chiip은 바꾸지 않는다) + Chiip 장부 월 $9(`knowledge/models/images/ledger.csv`).
- 구글 비용 기록이 최대 24시간 늦어 Chiip 장부가 먼저 멈춘다. 장부 한도를 넘으면 이미지 없이 리포트를 내고 `over_budget`.
- 구글이 결제·한도 오류(402·서비스 일시중지)를 주면 그달 생성을 모두 멈추고 `google_cap`. 마스터가 충전·한도를 확인한 뒤 `product_images.py resume`으로만 푼다.
- 산업 리포트 몫은 장부 한도의 40%(월 $3.6)까지 — 종목 리포트 이미지가 밀려나지 않게.

## 3. 일괄 처리 선주문
- 종목이 알파 감지 목록에 처음 오르면(`alpha_watch.evaluate_and_send`) 이미지를 Batch 모드로 미리 주문한다(가격 절반, 최대 24시간). 리포트 회차는 `fetch-batch`로 회수된 것만 쓴다 — 30분 제한 안에서 기다리지 않는다.
- 같은 회사 재분석·같은 제품은 캐시(설명문+모델+크기+보기 해시)로 0원. BOM as_of가 90일을 넘거나 BOM이 바뀌면 분해도만 다시.

## 4. 제품 단위 BOM 저장소 공유(산업판)
- 산업 리포트의 대표 제품(HBM4 적층, CoWoS 패키지, 800G 트랜시버 등)은 회사 datapack이 아니라 `knowledge/models/products/<slug>/bom.json`에 둔다. 종목 리포트가 같은 제품을 다루면 같은 이미지를 쓴다.
- BOM 표의 핵심은 부품별 공급사 지도다. 감시 목록 종목은 강조, 목록 밖 상장사는 '후보 메모'로 모은다(자동 편입 없음).
- 90일이 지나거나 새 세대가 나오면 새 slug로 만들고 옛 것은 지우지 않는다(세대 비교용).

## 5. 구현과 현재 상태
- 설정 `config/report_images.yaml` · 생성 `scripts/tenbagger/product_images.py`(plan·make·fetch-batch·ledger·resume, `--product`·`--pair`·`--view cross-section`)
- 검수 `scripts/tenbagger/image_check.py`(자동 항목 + Claude 눈 검수 `visual` + 처음 회사 5곳·산업 3건 텔레그램 승인)
- 블록 `scripts/tenbagger/image_view.py` → `report_html` `image`(base64 + SVG 번호 원·지시선)·`bom` 표, 번호 '사진 A·B·C'
- 자리: 종목 = 내러티브(제품·서비스) / 공급망 병목 첫머리(분해도 + BOM). 산업 = datapack `images[{section, product, condition}]`로 판정한 절 첫머리(`event_frame.place_images`, 판정 기록 `image_plan`)
- 텔레그램: `publish_tenbagger.py send --photo`(마스터 개인 봇만). 노션은 이미지 블록 업로드가 안 되면 "이미지는 리포트 보기 링크에서" 한 줄.
- 2026-11-08 첫 실제 호출(PSIX 제품 1장) → HTTP 402 "prepayment credits are depleted" — 과금 없음, 장부 `google_cap`. 마스터 충전 뒤 `resume`.
- webp 변환·축소에 Pillow가 필요하다. 설치 전에는 원본 형식으로 저장하고 검수에서 용량 경고가 난다.
