"""모델 포트폴리오 구성 2단계 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "pm"))
import construct as cs  # noqa: E402

C = {"expected": {"scenario_probs": [0.25, 0.5, 0.25], "ic": 0.05, "weights": {"pwr": 1 / 3, "grinold": 1 / 3, "conv": 1 / 3}, "k_kelly": 0.25, "rf": 0.04},
     "bl": {"lambda": 2.5, "tau": 0.05, "mrp": 0.05, "view_conf": 0.3}, "opt": {"kappa": 0.0, "step": 0.05},
     "overlay": {"w_max": 0.10, "theme_max": 0.35}}
S = [[0.09, 0.03], [0.03, 0.16]]


class T(unittest.TestCase):
    def test_inverse(self):
        I = cs.inv(S)
        p = [[sum(S[i][k] * I[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
        self.assertAlmostEqual(p[0][0], 1)
        self.assertAlmostEqual(p[0][1], 0)

    def test_bl_no_view_is_capm_prior(self):
        pi, post = cs.black_litterman(S, [1.0, 2.0], {}, {}, C)
        self.assertEqual(pi, post)
        self.assertAlmostEqual(pi[1], 0.10)

    def test_bl_view_moves_toward_q_by_confidence(self):
        _, lo = cs.black_litterman(S, [1.0, 1.0], {0: 0.30}, {0: 0.2}, C)
        _, hi = cs.black_litterman(S, [1.0, 1.0], {0: 0.30}, {0: 0.9}, C)
        self.assertLess(0.05, lo[0])
        self.assertLess(lo[0], hi[0])
        self.assertLess(hi[0], 0.30)

    def test_kelly_zero_when_negative_edge(self):
        self.assertEqual(cs.kelly3(100, [60, 90, 110], (0.25, 0.5, 0.25), 0.04), 0.0)
        self.assertGreater(cs.kelly3(100, [80, 130, 200], (0.25, 0.5, 0.25), 0.04), 0.0)

    def test_expected_conflict_zeroes(self):
        rep = {"ticker": "ZZZ_NONE", "bear": 50, "target": 90, "bull": 120}   # PWR 음수
        mu, parts = cs.expected(rep, 100, 0.4, 2.0, C)                      # 그리놀드 양수
        self.assertEqual(mu, 0.0)
        self.assertTrue(parts["conflict"])

    def test_optimize_respects_caps_and_budget(self):
        w = cs.optimize([0.5, 0.5], S, [0.10, 0.05], {"x": [0, 1]}, C)
        self.assertLessEqual(w[0], 0.10 + 1e-9)
        self.assertLessEqual(w[1], 0.05 + 1e-9)
        self.assertLessEqual(sum(w), 1 + 1e-9)


if __name__ == "__main__":
    unittest.main()
