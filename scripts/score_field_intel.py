"""필드 인텔 선행성·적중률 (BUILD_PROMPT §3.2, §17.4) — 월간. 식별정보 없이 source_class 단위.
사용: py scripts/score_field_intel.py
"""
import sys
from collections import defaultdict

from score_common import pct, read_csv


def main(argv):
    rows = read_csv("knowledge/field_intel_index.csv")
    by = defaultdict(lambda: {"n": 0, "confirmed": 0, "refuted": 0, "lead": []})
    for r in rows:
        k = r["source_class"]
        by[k]["n"] += 1
        if r["outcome"] == "confirmed":
            by[k]["confirmed"] += 1
            if r.get("lead_days"):
                by[k]["lead"].append(float(r["lead_days"]))
        elif r["outcome"] == "refuted":
            by[k]["refuted"] += 1
    print(f"[필드 인텔 트랙레코드] 전체 {len(rows)}건")
    print("| source_class | 건수 | 확인 | 부정 | 적중률(판정분) | 평균 선행일 |")
    print("|---|---|---|---|---|---|")
    for k, v in sorted(by.items()):
        decided = v["confirmed"] + v["refuted"]
        avg = f"{sum(v['lead'])/len(v['lead']):.1f}" if v["lead"] else "-"
        print(f"| {k} | {v['n']} | {v['confirmed']} | {v['refuted']} | {pct(v['confirmed'], decided)} | {avg} |")
    print("※ 적중률이 낮은 source_class는 출처 신뢰도 하향 '제안'(마스터 확정)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))