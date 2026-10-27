"""미국 정부 지표 (BUILD_PROMPT §13.8, §17.3.3) — 월간
정책 사건 단계 분포, 사전 공람 포착 건수, 코드명 매핑 적중률
사용: py scripts/score_usgov.py
"""
import json
import sys
from collections import Counter

from score_common import ROOT, pct, read_csv


def main(argv):
    ev = read_csv("knowledge/policy/policy_events.csv")
    print(f"[미국 정부] 정책 사건 {len(ev)}건 — 단계: " + ", ".join(f"{k} {v}" for k, v in Counter(r["stage"] for r in ev).items()))
    pi = 0
    for f in (ROOT / "radar" / "inbox").rglob("src-fedreg-pi*.json"):
        pi += 1
    print(f"- 관보 사전 공람 포착(보관 기간 내): {pi}건")
    cn = read_csv("knowledge/policy/codename_projects.csv")
    resolved = [r for r in cn if r.get("resolved_entity")]
    right = [r for r in resolved if r["resolved_entity"] in (r.get("candidates") or "").split(";")[:1]]
    print(f"- 코드명 프로젝트 {len(cn)}건, 실명 확인 {len(resolved)}건, 1순위 후보 적중 {pct(len(right), len(resolved))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))