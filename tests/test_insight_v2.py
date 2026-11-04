"""인사이트(해석 품질)·컨빅션(방향 적중 확률) 재설계 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "insight"))
import insight_calc as ic  # noqa: E402
import score_ledger as sl  # noqa: E402


class T(unittest.TestCase):
    def test_insight_is_interpretation_only(self):
        r = ic.interp(5, 2, 2, 2, 1)
        self.assertEqual(r["insight"], 10)   # 상한
        self.assertNotIn("materiality", r["points"])
        self.assertTrue(ic.interp(1, 0, 1, 0, 1)["fact_only"])

    def test_conviction_prior_is_probability(self):
        with mock.patch.object(ic, "calibration", return_value=None):
            self.assertEqual(ic.conviction2(3, 0, 0, 0, 0)["conviction"], 5.0)   # 원점수 0 = 동전 던지기
            hi = ic.conviction2(0, 2, 1, 2, 2)
            self.assertEqual((hi["raw"], hi["conviction"], hi["status"]), (10, 8.0, "보정 전"))

    def test_conviction_uses_adopted_calibration(self):
        with mock.patch.object(ic, "calibration", return_value={"a": -2.0, "b": 0.4, "n": 40}):
            self.assertAlmostEqual(ic.conviction2(0, 2, 1, 2, 2)["p_hit"], 0.881, places=3)
            self.assertEqual(ic.conviction2(3, 0, 0, 0, 0)["conviction"], 5.0)   # 5 아래로 내리지 않는다

    def test_logit_fit_learns_direction(self):
        xs = [i % 11 for i in range(220)]
        ys = [1 if (x >= 5 or i % 7 == 0) else 0 for i, x in enumerate(xs)]
        a, b = sl.logit_fit(xs, ys)
        self.assertGreater(b, 0)


if __name__ == "__main__":
    unittest.main()
