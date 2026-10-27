---
name: foreign-press-scan
description: 역방향 L9: 대만·중국·일본·해외 지역 언론 원문에서 T0 관련 수주·증설·인증 보도를 판정한다. 원문 보존 + 한국어 번역 병기, 인용은 원문 기준.
argument-hint: "[YYYYMMDD]"
---

# foreign-press-scan — 외국어 언론 (§11.4 L9)
1. `radar/reverse/collectors/foreign_press.py` 결과(Google News RSS 번체·간체·일본어 쿼리, 공개 범위).
2. 현지 언론 1차 취재 보도 = S3, 재인용·출처 불명 = S1~S2. 유료 매체는 헤드라인·공개 범위만.
3. 원문 제목·핵심 문장은 `original_excerpt`에 원어로, `gist_ko`는 번역 요지. **번역문은 증거가 아니다.**
4. 언어 차익: 국내 보도보다 먼저 나왔는지 기록(선행성 장부).
5. 신호 레코드: `docs/templates/signal.yaml`, id `py scripts/chiip_ids.py signal`, 저장 `radar/reverse/signals/YYYY/MM/`. 강도 S0~S5(§11.6), 대안 설명 필수, 원문 짧게 보존·번역 병기(번역은 증거 아님).
