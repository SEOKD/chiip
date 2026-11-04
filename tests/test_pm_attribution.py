"""모델 포트폴리오 성과 귀속·학습 4단계 시험 (마스터 지시 2026-11-04)"""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "pm"))
import attribution as at  # noqa: E402


class T(unittest.TestCase):
    def test_perf_basic(self):
        r = {f"2026-01-{i:02d}": 0.01 for i in range(1, 11)}
        p = at.perf(r, 0.0)
        self.assertAlmostEqual(p["cum"], 1.01 ** 10 - 1, places=4)
        self.assertEqual(p["max_dd"], 0.0)

    def test_dsr_falls_with_more_trials(self):
        one = at.dsr(0.1, 250, 0.0, 3.0, [0.1])
        many = at.dsr(0.1, 250, 0.0, 3.0, [0.1, 0.0, -0.05, 0.08, 0.02, 0.06])
        self.assertGreater(one, many)
        self.assertGreater(one, 0.9)

    def test_min_trl(self):
        self.assertIsNone(at.min_trl(-0.01, 0, 3))
        self.assertGreater(at.min_trl(0.05, 0, 3), at.min_trl(0.2, 0, 3))   # 샤프가 작을수록 더 오래 봐야 한다

    def test_spearman(self):
        self.assertAlmostEqual(at.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(at.spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)

    def test_factor_regression_recovers_beta(self):
        rnd = random.Random(3)
        m = [rnd.gauss(0, 0.01) for _ in range(300)]
        y = [0.0002 + 1.5 * x + rnd.gauss(0, 0.001) for x in m]
        coef = at.ols_multi(y, [m])
        self.assertAlmostEqual(coef[1], 1.5, places=1)


if __name__ == "__main__":
    unittest.main()
