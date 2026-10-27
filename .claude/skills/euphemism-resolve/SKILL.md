---
name: euphemism-resolve
description: 상대방 자료의 익명 표현('a leading Korean memory supplier', 'Customer A', '韩系大厂')을 후보 실체로 매핑한다. 경쟁 가설 분석(ACH) 표로 일치·불일치 증거를 대조하며 결과는 가설이다.
argument-hint: "[신호 id 또는 문구]"
---

# euphemism-resolve — 완곡어 해석 (§11.7, P17)
1. 익명 표현과 문맥(지역·제품·규모·시점) 추출.
2. 조건을 만족하는 후보 실체 나열(`config/lexicon/*`의 euphemisms 참고).
3. ACH 표:
   | 증거 | 후보A | 후보B | 후보C |
   (매출 비중 대비 후보의 구매 규모, 지역 매출 분해, 과거 공시의 실명 노출, 제품 사양·시점, 다른 레이어 신호) — 일치(+)·불일치(−)·무관(0).
4. 결론: "Customer A는 ○○일 가능성이 높음 (일치 n, 불일치 m, 가정: …)". 확률을 쓰면 가정임을 표시.
5. 신호 레코드 `euphemism_resolution`에 요약, red-team에 반대 후보 검토 요청.
