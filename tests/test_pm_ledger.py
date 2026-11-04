"""모델 포트폴리오 가상 장부 3단계 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "pm"))
import ledger as lg  # noqa: E402

C = {"ledger": {"band": 0.20, "band_abs": 0.005, "speed": 0.5, "half_spread_bps": 10, "eta": 0.5, "nav_usd": 1_000_000}}


class T(unittest.TestCase):
    def test_mark_drifts_weights_and_nav(self):
        bk = {"nav": 1.0, "w": {"A": 0.5}}
        out = lg.mark(bk, {"A": {"d1": 0.10}}, ["d1"], 0.0)
        self.assertAlmostEqual(out[0][1], 0.05)
        self.assertAlmostEqual(bk["nav"], 1.05)
        self.assertAlmostEqual(bk["w"]["A"], 0.55 / 1.05)

    def test_band_skips_small_gap(self):
        bk = {"nav": 1.0, "w": {"A": 0.10}}
        to, co = lg.rebalance(bk, {"A": 0.11}, C, {}, {})
        self.assertEqual((to, co), (0.0, 0.0))

    def test_partial_adjust_and_cost(self):
        bk = {"nav": 1.0, "w": {"A": 0.10}}
        to, co = lg.rebalance(bk, {"A": 0.30}, C, {}, {})
        self.assertAlmostEqual(bk["w"]["A"], 0.20)            # 절반만
        self.assertAlmostEqual(co, 0.10 * 10 / 1e4)            # 스프레드만(거래량 모름)
        self.assertAlmostEqual(bk["nav"], 1 - co)

    def test_new_and_exit_move_fully(self):
        bk = {"nav": 1.0, "w": {"A": 0.10}}
        lg.rebalance(bk, {"B": 0.05}, C, {}, {})
        self.assertNotIn("A", bk["w"])
        self.assertAlmostEqual(bk["w"]["B"], 0.05)

    def test_impact_when_volume_known(self):
        bk = {"nav": 1.0, "w": {}}
        _, co = lg.rebalance(bk, {"A": 0.10}, C, {"A": 0.03}, {"A": 10_000_000})
        self.assertGreater(co, 0.10 * 10 / 1e4)


if __name__ == "__main__":
    unittest.main()
