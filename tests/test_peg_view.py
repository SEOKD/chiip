"""성장주 PEG (마스터 지시 2026-11-08)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import peg_view as pv  # noqa: E402

DP = {"multiples_now": {"pe_fwd": 30.0, "pe_fwd2": 20.0},
      "peers": [{"ticker": "A", "pe_fwd": 20.0, "pe_fwd2": 16.0}, {"ticker": "B", "pe_fwd": 40.0, "pe_fwd2": 20.0}, {"ticker": "C", "pe_fwd": -5.0, "pe_fwd2": 10.0}]}


class TestPEG(unittest.TestCase):
    def test_growth_from_forward_pe_and_peg(self):
        c = pv.compute(DP, "X")
        self.assertAlmostEqual(c["growth"], 0.5)          # 30 ÷ 20 − 1
        self.assertAlmostEqual(c["peg"], 0.6)             # 30 ÷ 50
        self.assertAlmostEqual(c["peer_median"], (0.8 + 0.4) / 2)   # A 20÷25, B 40÷100, C는 적자라 뺀다

    def test_not_growth_stock_has_no_peg(self):
        d = {**DP, "multiples_now": {"pe_fwd": 15.0, "pe_fwd2": 14.0}}   # 성장 7% < 15%
        self.assertFalse(pv.compute(d)["is_growth"])
        self.assertEqual(pv.blocks(d), [])

    def test_blocks(self):
        B = pv.blocks(DP, "X")
        self.assertIn("PEG 0.60", B[0]["text"])
        self.assertEqual(B[1]["rows"][0][0], "**X**")
        self.assertEqual(B[2]["chart"]["kind"], "hbars")


if __name__ == "__main__":
    unittest.main()
