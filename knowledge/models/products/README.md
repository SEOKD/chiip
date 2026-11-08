# 제품 단위 BOM 저장소 (마스터 지시 2026-11-08 산업 리포트 이미지 지시서 2절, ADR-017 §4)

`<slug>/bom.json` + `<slug>/images/`. 산업·테마 리포트와 종목 리포트가 같은 제품을 다루면 같은 파일·같은 이미지를 쓴다.
slug 예: `hbm4-12hi`, `cowos-l-package`, `transceiver-800g-osfp`, `cpo-engine`, `ai-server-rack-gb300`

```json
{"product": "HBM4 12단(일반형)", "product_en": "HBM4 12-high stack", "as_of": "2026-11-08", "layers_order": "위→아래",
 "items": [
   {"no": 1, "part": "코어 D램 다이(12개)", "part_en": "twelve stacked DRAM core dies", "role": "저장",
    "suppliers": [{"name": "SK하이닉스", "ticker": "000660", "share_note": "공개 자료상 1위", "source": "URL"}],
    "chiip_ids": ["kr-skhynix"], "source": "URL", "confidence": "확인"},
   {"no": 9, "part": "TC 본더", "role": "적층 공정", "kind": "장비", "suppliers": [], "confidence": "추정"}],
 "source_note": "출처 목록", "used_by": ["industry:hbm-2026-11", "company:kr-skhynix"]}
```

- `confidence`는 `확인`·`추정`만. 분해도 이름표에는 `확인`만, `추정`은 표에 회색으로. `확인`이 6개 미만이면 분해도 없이 표만.
- `chiip_ids`는 `suppliers`와 같은 순서. 감시 목록 종목은 표에서 강조, 목록 밖 상장사는 '후보 메모'(자동 편입 없음).
- `kind: 장비|소재`는 분해도에 그리지 않고 표의 '공정·장비' 구역에만.
- 점유율·원가 비중은 출처가 있을 때만, 없으면 "미공개", 추정이면 "추정".
- 유료 리포트 원문·표 복제 금지(요지·출처만). 노션 IB 요지는 대조용 — 표 출처로 쓰지 않는다. 마스터 필드 메모는 로컬 대조에만.
- 90일 안이면 그대로 쓰고, 지나거나 새 세대가 나오면 새 slug(옛 것은 지우지 않는다 — 세대 비교).
