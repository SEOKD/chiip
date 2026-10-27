"""역방향 레이더 성과 (BUILD_PROMPT §11.13, §17.3.1) — 주간·월간
선포착률·평균 선행일(레이어·원천별), 수렴 경보 정밀도, 계정 평판 상·하위
사용: py scripts/score_reverse.py
"""
import sys
from collections import defaultdict
from pathlib import Path

import yaml
from score_common import ROOT, pct, read_csv


def main(argv):
    ledger = read_csv("knowledge/lead_time_ledger.csv")
    by_layer = defaultdict(list)
    hits = sum(1 for r in ledger if r["outcome"] == "confirmed")
    for r in ledger:
        if r["outcome"] == "confirmed" and r.get("lead_days"):
            by_layer[r["layer"]].append(float(r["lead_days"]))
    alerts = confirmed_alerts = 0
    for f in (ROOT / "radar" / "reverse" / "signals").rglob("*.yaml"):
        s = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if s.get("status") in ("수렴경보", "승격", "부정"):
            alerts += 1
            if (s.get("resolved") or {}).get("result") == "확인" if isinstance(s.get("resolved"), dict) else False:
                confirmed_alerts += 1
    print(f"[역방향 레이더] 장부 {len(ledger)}건, 공식 확인 {hits}건")
    for layer, v in sorted(by_layer.items()):
        print(f"- {layer}: 평균 선행 {sum(v)/len(v):.1f}일 (n={len(v)})")
    print(f"- 경보 정밀도: {pct(confirmed_alerts, alerts)} ({confirmed_alerts}/{alerts})")
    rep = sorted(read_csv("knowledge/handle_reputation.csv"), key=lambda r: -int(r.get("confirmed") or 0))
    if rep:
        print("- 계정 평판 상위: " + ", ".join(f"{r['platform']}:{r['handle']}" for r in rep[:5]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))