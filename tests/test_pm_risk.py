"""모델 포트폴리오 위험 엔진 1단계 시험 (마스터 지시 2026-11-04)"""
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "pm"))
import risk as r  # noqa: E402


def sample(n=200, k=4, seed=1):
    rnd = random.Random(seed)
    X = []
    for _ in range(n):
        m = rnd.gauss(0, 0.01)
        X.append([m + rnd.gauss(0, 0.01 * (j + 1)) for j in range(k)])
    return X


class T(unittest.TestCase):
    def test_shrink_delta_in_unit_interval(self):
        S, d = r.shrunk_cov(sample(), 63)
        self.assertTrue(0 <= d <= 1)
        self.assertTrue(all(S[i][i] > 0 for i in range(4)))

    def test_inverse_vol_favors_low_vol(self):
        S, _ = r.shrunk_cov(sample(), 63)
        w = r.inv_vol(S)
        self.assertAlmostEqual(sum(w), 1.0)
        self.assertGreater(w[0], w[3])

    def test_erc_equalizes_risk_contribution(self):
        S, _ = r.shrunk_cov(sample(), 63)
        w = r.erc(S)
        m = r.matvec(S, w)
        rc = [w[i] * m[i] for i in range(4)]
        self.assertLess(max(rc) / min(rc), 1.02)

    def test_hrp_sums_to_one_and_positive(self):
        S, _ = r.shrunk_cov(sample(k=6), 63)
        w = r.hrp(S)
        self.assertAlmostEqual(sum(w), 1.0)
        self.assertTrue(all(x > 0 for x in w))

    def test_overlay_scales(self):
        X = sample()
        S, _ = r.shrunk_cov(X, 63)
        names = list("abcd")
        c = {"risk": {"annualize": 252}, "overlay": {"sigma_target": 0.20, "dd_max": 0.25, "w_max": 0.10, "cvar_q": 0.95}}
        st = r.port_stats([0.25] * 4, S, X, names, {n: {"beta": 1.0, "themes": {}} for n in names}, c)
        self.assertLessEqual(st["vol_target_scale"], 1.0)
        self.assertTrue(0 <= st["dd_control_scale"] <= 1)
        self.assertEqual(st["over_w_max"], names)   # 25% > 10% 상한 — 1단계는 표시만
        self.assertAlmostEqual(sum(st["risk_contrib"].values()), 1.0, places=2)


if __name__ == "__main__":
    unittest.main()
