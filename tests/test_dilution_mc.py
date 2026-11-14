"""전환사채 판정(이중 반영 방지)·몬테카를로 1년차 충격(시나리오 사이 분산 차감) — ADR-041"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
import build_drivers  # noqa: E402
import montecarlo  # noqa: E402


class TestConverts(unittest.TestCase):
    def test_in_the_money_physical_moves_principal_out_of_debt(self):
        sh, debt_out, why = build_drivers.convert_terms([{"name": "2030 CB", "principal": 0.735, "conv_price": 27.0, "settlement": "physical"}], 29.14)
        self.assertAlmostEqual(sh, 0.735 / 27.0)
        self.assertAlmostEqual(debt_out, 0.735)
        self.assertIn("내가격", why)

    def test_out_of_the_money_stays_debt(self):   # 비셰이형: 전환가가 가격보다 높으면 주식이 아니라 차입
        sh, debt_out, why = build_drivers.convert_terms([{"principal": 0.735, "conv_price": 32.0}], 29.14)
        self.assertEqual((sh, debt_out), (0.0, 0.0))
        self.assertIn("외가격", why)

    def test_net_share_settlement_only_excess(self):   # Veeco·Cohu형: 원금은 현금, 초과분만 주식
        sh, debt_out, _ = build_drivers.convert_terms([{"principal": 0.23, "conv_price": 29.22, "shares": 0.00787, "settlement": "net_share"}], 36.0)
        self.assertAlmostEqual(sh, 0.00787 * (1 - 29.22 / 36.0))
        self.assertEqual(debt_out, 0.0)

    def test_missing_terms_are_reported_not_guessed(self):
        sh, debt_out, why = build_drivers.convert_terms([{"name": "X", "principal": 0.1}], 10.0)
        self.assertEqual((sh, debt_out), (0.0, 0.0))
        self.assertIn("판정 못 함", why)


class TestWithinFactor(unittest.TestCase):
    def test_floor_when_scenarios_cover_the_range(self):
        sc = {"bear": {"prob": 0.25, "growth": {"start": 0.0}}, "base": {"prob": 0.5, "growth": {"start": 0.1}}, "bull": {"prob": 0.25, "growth": {"start": 0.2}}}
        self.assertAlmostEqual(montecarlo.within_factor(sc, 0.05), 0.25)   # 시나리오 사이 σ 0.071 > 0.05 → 하한

    def test_partial_when_scenarios_are_narrow(self):
        sc = {"bear": {"prob": 0.25, "growth": {"start": 0.09}}, "base": {"prob": 0.5, "growth": {"start": 0.1}}, "bull": {"prob": 0.25, "growth": {"start": 0.11}}}
        f = montecarlo.within_factor(sc, 0.05)
        var_b = 0.5 * 0.01 ** 2
        self.assertAlmostEqual(f, (0.05 ** 2 - var_b) ** 0.5 / 0.05)
        self.assertLess(f, 1.0)


if __name__ == "__main__":
    unittest.main()
