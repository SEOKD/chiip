"""역방향 신호 가중치 조정 '제안' (BUILD_PROMPT §11.6, §11.13) — 자동 반영하지 않는다(마스터 승인)

lead_time_ledger.csv의 원천·레이어별 확인율·평균 선행일로 source_reliability 배수를 제안.
제안 배수 = 0.5 + 확인율(0~1) (표본 5건 미만은 1.0 유지)
사용: py scripts/propose_weights.py
"""
import sys
from collections import defaultdict

from score_common import read_csv


def main(argv):
    rows = read_csv("knowledge/lead_time_ledger.csv")
    by = defaultdict(lambda: [0, 0, []])
    for r in rows:
        k = (r["layer"], r["source_id"])
        by[k][0] += 1
        if r["outcome"] == "confirmed":
            by[k][1] += 1
            if r.get("lead_days"):
                by[k][2].append(float(r["lead_days"]))
    print("| 레이어 | 원천 | 표본 | 확인 | 평균 선행일 | 제안 배수 |")
    print("|---|---|---|---|---|---|")
    for (layer, src), (n, ok, leads) in sorted(by.items()):
        mult = 1.0 if n < 5 else round(0.5 + ok / n, 2)
        avg = f"{sum(leads)/len(leads):.1f}" if leads else "-"
        print(f"| {layer} | {src} | {n} | {ok} | {avg} | {mult} |")
    if not by:
        print("(선행성 장부가 비어 있음 — 신호가 공식 확인·부정될 때 쌓인다)")
    print("※ 제안일 뿐. 반영하려면 config/signal_rules.yaml에 마스터가 승인 후 기록")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))