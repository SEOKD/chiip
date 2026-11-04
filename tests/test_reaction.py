"""실적 반응 합리성 엔진 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "insight"))
import reaction as rx  # noqa: E402

BASE = {"beta": 1.0, "surprise": {"eps": 8.0, "rev": 2.0, "guide": 2.0}, "pre_drift20": 0.0, "history": []}


def run(stock, **kw):
    d = {**BASE, "reaction": {"stock": stock, "market": 0.0, "peers": None, "extended": None}, **kw}
    return rx.quant(d)


class T(unittest.TestCase):
    def test_expected_reaction_positive_for_beat_and_raise(self):
        self.assertGreater(run(0)["expected_ar"], 0)

    def test_rational_when_close(self):
        q = run(run(0)["expected_ar"])
        self.assertEqual(q["kind"], "합리적")
        self.assertGreaterEqual(q["quant_score"], 9.9)

    def test_direction_gap(self):
        q = run(-15)
        self.assertTrue(q["kind"].startswith("방향 괴리"))
        self.assertLess(q["quant_score"], 6)

    def test_over_and_under(self):
        self.assertTrue(run(30)["kind"].startswith("과잉반응"))
        self.assertTrue(run(0.1, surprise={"eps": 40, "rev": 10, "guide": 10})["kind"].startswith("과소반응"))

    def test_runup_lowers_expectation(self):
        self.assertLess(run(0, pre_drift20=15)["expected_ar"], run(0)["expected_ar"])

    def test_panel_median_iqr_and_redteam_cap(self):
        p = rx.panel({"rounds": [{"round": 1, "scores": {"a": 3, "b": 5, "c": 7, "d": 9, "e": 10}},
                                 {"round": 2, "scores": {"a": 6, "b": 6, "c": 7, "d": 7, "e": 8}}], "redteam": {"adjust": -5}})
        self.assertEqual(p["rounds"][1]["median"], 7.0)
        self.assertTrue(p["converged"])
        self.assertEqual(p["redteam_adjust"], -1.5)
        self.assertEqual(p["final"], 5.5)


if __name__ == "__main__":
    unittest.main()
