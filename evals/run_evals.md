# 회귀 사례 실행 방법

1. `evals/cases/`의 각 사례 prompt를 치입에게 그대로 묻는다.
2. 답변이 failure_pattern에 해당하면 실패, expected_behavior를 만족하면 통과.
3. expected_behavior가 빈 사례는 마스터가 정답 기준을 채운 뒤부터 채점한다.
4. 마스터가 오류를 지적하면: 사례 추가 → 스킬·규칙 수정 → 재실행(§17.5).
