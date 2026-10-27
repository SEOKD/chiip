"""예측 원장 채점 (BUILD_PROMPT §5.9) — 만기 도래·브라이어 점수
사용: py scripts/score_predictions.py
"""
import sys
from datetime import date

from score_common import parse_date, read_csv


def main(argv):
    rows = read_csv("knowledge/predictions.csv")
    due = [r for r in rows if not r["resolved_on"] and (parse_date(r["deadline"]) or date.max) <= date.today()]
    scored = [r for r in rows if r["outcome"] in ("1", "0", "true", "false")]
    brier = [(float(r["probability"]) - (1.0 if r["outcome"] in ("1", "true") else 0.0)) ** 2
             for r in scored if r.get("probability")]
    print(f"[예측 원장] 전체 {len(rows)}, 판정 {len(scored)}, 만기 도래 미판정 {len(due)}")
    for r in due:
        print(f"- 판정 필요: {r['pred_id']} {r['statement']} (기한 {r['deadline']})")
    if brier:
        print(f"- 브라이어 점수(낮을수록 좋음): {sum(brier)/len(brier):.3f} (n={len(brier)})")
    print("※ 사후 수정 금지 — 정정은 새 행으로")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))