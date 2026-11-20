"""내 종목 장부 판정 — 재채점 먼저, 관심 알파 미달은 직접 지정·pin도 제외, 보유는 재점검(마스터 지시 2026-11-20)"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "portfolio"))
import book as B  # noqa: E402

CFG = {"stale_days": 14, "alpha_min": 6.0}
H = [{"id": "a", "ticker": "A", "status": "관심", "pin": True}, {"id": "b", "ticker": "B", "status": "관심"},
     {"id": "c", "ticker": "C", "status": "보유"}, {"id": "d", "ticker": "D", "status": "관심"}, {"id": "e", "ticker": "E", "status": "종료"}]
AL = {"a": {"total": 5.2, "scored_on": "20261115"}, "b": {"total": 7.1, "scored_on": "20261115"}, "c": {"total": 4.0, "scored_on": "20261115"},
      "d": {"total": 3.0, "scored_on": "20261020"}}


class Book(unittest.TestCase):
    def test_verdicts(self):
        v = {r["ticker"]: r["verdict"] for r in B.judge(H, AL, {}, {}, CFG, date(2026, 11, 20))}
        self.assertEqual(v, {"A": "제외", "B": "유지", "C": "재점검", "D": "재채점"})

    def test_end_block(self):
        t = "holdings:\n  - id: a\n    ticker: A\n    status: 관심\n    pin: true\n  - id: b\n    status: 관심\n"
        out, ok = B.end_block(t, "a", "2026-11-20", "알파 5.2 < 6.0")
        self.assertTrue(ok)
        self.assertIn("    status: 종료\n    ended: 2026-11-20\n", out)
        self.assertIn("  - id: b\n    status: 관심\n", out)


if __name__ == "__main__":
    unittest.main()
