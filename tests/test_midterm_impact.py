"""중간선거 이후 영향 점수 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "policy"))
import midterm_impact as mi  # noqa: E402

C = mi.cfg()
UNI = {"X": {"id": "nope-x", "ticker": "X", "sub": "solar", "market": "us"}, "Y": {"id": "nope-y", "ticker": "Y", "sub": "oil_gas", "market": "other"}}


class T(unittest.TestCase):
    def test_sign_and_bounds(self):
        up = mi.score("X", C, UNI, {"AMEX:TAN": {"car": 0.03, "t": 2.0}})
        dn = mi.score("Y", C, UNI, {"AMEX:XOP": {"car": -0.02, "t": -1.0}})
        self.assertGreater(up["score"], 0)
        self.assertLess(dn["score"], 0)
        self.assertTrue(-10 <= up["score"] <= 10)

    def test_non_us_scaled(self):
        a = mi.score("Y", C, UNI, {})
        self.assertAlmostEqual(a["policy"], C["policy_channels"]["fossil_permitting"]["score"] * 0.5)

    def test_reaction_cap(self):
        r = mi.score("X", C, UNI, {"AMEX:TAN": {"car": 0.5, "t": 99}})
        self.assertEqual(r["reaction"], C["impact"]["reaction_cap"])


if __name__ == "__main__":
    unittest.main()
