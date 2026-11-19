"""알파 감지 보고 — 직전 보고 대비 ±0.5 이상일 때만(마스터 지시 2026-11-19)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
import alpha_watch as A  # noqa: E402


class Delta(unittest.TestCase):
    def test_gate(self):
        st = {"x": {"alpha": 5.6}}
        self.assertFalse(A.should_report("x", 5.9, st))
        self.assertTrue(A.should_report("x", 6.1, st))
        self.assertTrue(A.should_report("x", 5.1, st))
        self.assertTrue(A.should_report("new", 5.2, st))
        self.assertFalse(A.should_report("x", None, st))


if __name__ == "__main__":
    unittest.main()
