"""인재·조직 지표 (BUILD_PROMPT §12.8, §17.3.2) — 월간
사업장·직무별 채용 지수 추이, 신규 키워드 첫 등장, org_changes 건수
사용: py scripts/score_talent.py
"""
import sys
from collections import Counter

from score_common import ROOT, read_csv


def main(argv):
    hi = read_csv("knowledge/models/hiring_index.csv")
    print(f"[인재·조직] 채용 집계 {len(hi)}행")
    agg = Counter()
    for r in hi:
        agg[(r["company"], r["site"], r["function"])] += int(r.get("new_postings") or 0)
    for (c, s, fn), n in agg.most_common(10):
        print(f"- {c} {s} {fn}: 신규 공고 {n}")
    kws = [k for r in hi for k in (r.get("new_keywords") or "").split(";") if k]
    if kws:
        print("- 첫 등장 키워드: " + ", ".join(sorted(set(kws))))
    for f in (ROOT / "knowledge" / "org").glob("*/org_changes.csv"):
        n = len(read_csv(f.relative_to(ROOT).as_posix()))
        print(f"- {f.parent.name} 조직 변경 {n}건")
    print("※ 채용은 의도 신호. 사업장 채용 지수 vs 이후 CAPEX·램프 발표 시차는 데이터가 쌓인 뒤 백테스트(6단계)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))