"""섹터 배분 판단 체계 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "pm"))
import sector_alloc as sa  # noqa: E402

C = sa.cfg()


class T(unittest.TestCase):
    def test_aggregate_cap_weighted_momentum(self):
        c = {"sectors": {"A": {"keys": ["k1", "k2"]}}}
        rows = {"k1": {"mcap_b": 300, "r21": 0.0, "r126": 0.1, "r252": 0.2, "above200": 1, "evs_pct3y": 0.2, "rev30": 0.01},
                "k2": {"mcap_b": 100, "r21": 0.0, "r126": 0.0, "r252": 0.0, "above200": 0, "evs_pct3y": 0.8, "rev30": -0.01}}
        a = sa.aggregate(c, rows)["A"]
        self.assertAlmostEqual(a["mom_12_1"], 0.15)
        self.assertAlmostEqual(a["above200"], 0.75)

    def test_regime_flags_and_tilts(self):
        flags, tilt = sa.regime(C, {"vix": {"last": 30}, "sp500": {"dd": -0.05}, "us10y": {"d20": 0.30}})
        self.assertEqual(flags, ["risk_off", "rates_up"])
        self.assertGreater(tilt["필수소비재"], 0)
        self.assertLess(tilt["유틸리티"], 1)   # 위험 회피 +1, 금리 상승 −1

    def test_mvo_budget_and_bounds(self):
        S = [[0.04, 0.01, 0.0], [0.01, 0.09, 0.0], [0.0, 0.0, 0.02]]
        bench = [0.5, 0.3, 0.2]
        w = sa.mvo([0.10, 0.0, 0.0], S, bench, {**C["allocation"], "active_max": 0.10, "w_max": 0.6}, iters=3000)
        self.assertAlmostEqual(sum(w), 1.0, places=4)
        for wi, b in zip(w, bench):
            self.assertLessEqual(abs(wi - b), 0.10 + 1e-6)
        self.assertGreater(w[0], bench[0])

    def test_zscore_clip(self):
        z = sa.zs({"a": 0.0, "b": 0.0, "c": 0.0, "d": 100.0})
        self.assertLessEqual(max(z.values()), 3.0)


if __name__ == "__main__":
    unittest.main()
