"""구매 등급 성과 원장 시험 (마스터 지시 2026-11-04)"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import rating_ledger as rl  # noqa: E402

R = {"strong_buy": {"upside": 0.40, "rr": 3.0, "dcf_min": 0.0}, "buy": {"upside": 0.15, "rr": 1.5, "dcf_min": -0.5},
     "neutral": {"upside": -0.10}, "sell": {"upside": -0.30}}
V = {"strong_buy": 1.0, "buy": 0.375, "neutral": -0.25, "sell": -0.75}


class T(unittest.TestCase):
    def test_rule_matches_layout(self):
        self.assertEqual(rl.rule(-0.1011, 0.8, 0, R), "Sell")   # PWR 2026-11-02 — 경계 0.11%p 밖
        self.assertEqual(rl.rule(0.50, 14.9, 0.1, R), "Strong Buy")

    def test_hysteresis_holds_near_edge(self):
        self.assertEqual(rl.hyst(-0.1011, 0.8, 0, R, "Neutral", 0.02), "Neutral")
        self.assertEqual(rl.hyst(-0.20, 0.8, 0, R, "Neutral", 0.02), "Sell")
        self.assertEqual(rl.hyst(-0.1011, 0.8, 0, R, None, 0.02), "Sell")

    def test_volz(self):
        self.assertEqual(rl.volz(0.20, 0.80, V), "Neutral")   # 변동성 80% 종목의 +20%는 Buy가 아니다
        self.assertEqual(rl.volz(0.20, 0.25, V), "Buy")
        self.assertEqual(rl.volz(0.20, None, V), "")

    def test_excess(self):
        days = [f"2026-01-{i:02d}" for i in range(1, 11)]
        self.assertEqual(rl.excess([[d, 100 + i] for i, d in enumerate(days)], [[d, 100] for d in days], "2026-01-02", 3), 3.0)

    def test_fit_empty(self):
        rl.LEDGER = Path(tempfile.mkdtemp()) / "x.csv"
        self.assertEqual(rl.fit()["n"], 0)


if __name__ == "__main__":
    unittest.main()
