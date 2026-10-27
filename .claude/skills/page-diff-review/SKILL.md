---
name: page-diff-review
description: 역방향 L7 웹 변경과 침묵 탐지 결과를 판정한다: 고객·파트너 페이지 로고·문구 추가/삭제, 공급사 명단, 협력사 시상, 신규 데이터시트, 기준선 대비 사라진 언급. 대안 설명(단순 개편)을 반드시 적는다.
argument-hint: "[YYYYMMDD]"
---

# page-diff-review — 웹 변경·침묵 (§11.4 L7, §11.8)
1. `radar/reverse/collectors/page_diff.py` 결과(`radar/reverse/inbox/*/src-page-diff*`)의 추가·삭제 줄.
2. 추가: 파트너·고객 목록에 T0 등장 = S3(공식 페이지), 협력사 시상 = S4(상대방 실명 공식 발표).
3. 삭제·소멸(침묵): S2. 대안 설명(사이트 개편·문구 정리) 필수, 확인 질문 작성.
4. 감시 대상 추가는 `config/page_watch.yaml`(마스터 승인).
5. 신호 레코드: `docs/templates/signal.yaml`, id `py scripts/chiip_ids.py signal`, 저장 `radar/reverse/signals/YYYY/MM/`. 강도 S0~S5(§11.6), 대안 설명 필수, 원문 짧게 보존·번역 병기(번역은 증거 아님).
