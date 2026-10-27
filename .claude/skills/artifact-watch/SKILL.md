---
name: artifact-watch
description: 역방향 L5 기술 아티팩트 변화를 판정한다: 리눅스 커널·드라이버 패치, PCI ID 등록, 유통사 신규 부품번호·데이터시트, OCP 사양 기여. 자동 수집이 금지된 사양 DB·QVL·분해 정보는 마스터 수동 확인분만.
argument-hint: "[대상]"
---

# artifact-watch — 기술 아티팩트 (§11.4 L5, §21.6)
1. 자동 수집 허용 원천: 공개 메일링리스트·공개 Git 저장소, PCI ID 공개 저장소, 유통사 공식 API(허용 시), OCP 공개 사양.
2. **자동 수집 제외**(§21.6): TechPowerUp 등 사양 DB, 벤더 QVL 페이지, ImportYeti — 마스터가 확인해 붙여 준 내용만 판정.
3. 판정: 신규 장치 ID·메모리/CXL 장치 지원 코드·특정 벤더 대응 = 출시 전 하드웨어 정황(S2), 데이터시트 공개 = S3.
4. 신호 레코드: `docs/templates/signal.yaml`, id `py scripts/chiip_ids.py signal`, 저장 `radar/reverse/signals/YYYY/MM/`. 강도 S0~S5(§11.6), 대안 설명 필수, 원문 짧게 보존·번역 병기(번역은 증거 아님).
