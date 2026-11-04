"""SPAC 과거 표본·기저율 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import spac_history as sh  # noqa: E402


class T(unittest.TestCase):
    def test_summary_rates(self):
        rs = [{"r6m": "-0.6", "r12m": "-0.7", "r24m": "-0.9", "max24m": "1.0"},
              {"r6m": "0.1", "r12m": "0.2", "r24m": "1.5", "max24m": "3.2"},
              {"r6m": "0.5", "r12m": "9.5", "r24m": "", "max24m": "11"}]
        s = sh.summarize(rs)
        self.assertEqual(s["r24m"]["n"], 2)
        self.assertAlmostEqual(s["max24m"]["ge3x"], 2 / 3, places=3)
        self.assertAlmostEqual(s["max24m"]["ge10x"], 1 / 3, places=3)
        self.assertAlmostEqual(s["r12m"]["lt_minus50"], 1 / 3, places=3)

    def test_quantile_bounds(self):
        self.assertEqual(sh.q([1, 2, 3], 0.0), 1)
        self.assertEqual(sh.q([1, 2, 3], 1.0), 3)
        self.assertIsNone(sh.q([], 0.5))


if __name__ == "__main__":
    unittest.main()
