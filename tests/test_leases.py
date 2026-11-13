"""v2 엔진 리스 일관 처리 — 방식 A(ADR-026, 마스터 지시 2026-11-13)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
import dcf  # noqa: E402
import leases  # noqa: E402
import scenarios  # noqa: E402


def dp(debt, lease=(0.1, 2.7), nonlease=(0.03, 1.46), extra=None):
    bs = {"debt_current": nonlease[0], "debt_lt": nonlease[1], "lease_current": lease[0], "lease_lt": lease[1]}
    return {"profile": {"debt": debt}, "raw": {"balance_2026_09_30": bs}, **(extra or {})}


def co(net_debt=1.0):
    return {"rev0": 3.4, "ic0": 7.4, "tax": 0.25, "horizon": 10, "unit_usd": 1e9, "plus": False,
            "market": {"net_debt": net_debt, "shares": 0.23, "price": 45.0},
            "scenarios": {"base": {"growth": {"start": 0.1, "end": 0.035, "decay": 0.8}, "margin": {"m0": 0.17, "target": 0.18, "year_target": 3}, "s2c": 0.55}}}


class TestInfo(unittest.TestCase):
    def test_detects_lease_outside_debt(self):
        li = leases.info(dp(1.49))
        self.assertAlmostEqual(li["liab"], 2.8)
        self.assertFalse(li["in_debt"])

    def test_detects_lease_inside_debt(self):
        li = leases.info(dp(1.49 + 2.8))
        self.assertTrue(li["in_debt"])
        self.assertAlmostEqual(li["nonlease_debt"], 1.49, places=6)

    def test_no_lease_no_change(self):
        self.assertIsNone(leases.info(dp(1.0, lease=(0, 0))))
        c = co()
        self.assertIsNone(leases.apply(c, dp(1.0, lease=(0, 0)), 0.045))
        self.assertNotIn("lease", c)

    def test_override_and_opt_out(self):
        li = leases.info(dp(1.49, extra={"leases": {"liab": 3.0, "rate": 0.09, "in_debt": False}}))
        self.assertEqual((li["liab"], li["rate"]), (3.0, 0.09))
        self.assertIsNone(leases.info(dp(1.49, extra={"leases": False})))


class TestApply(unittest.TestCase):
    def test_outside_debt_adds_liability_and_interest(self):
        c = co(1.18)
        L = leases.apply(c, dp(1.49, extra={"leases": {"rate": 0.0928}}), 0.045)
        self.assertAlmostEqual(c["market"]["net_debt"], 1.18 + 2.8)
        self.assertAlmostEqual(L["interest"], 2.8 * 0.0928)
        self.assertAlmostEqual(L["margin_add"], 2.8 * 0.0928 / 3.4)
        self.assertAlmostEqual(c["pretax_kd"], (1.49 * 0.06 + 2.8 * 0.0928) / (1.49 + 2.8))   # 일반 차입·리스 잔액 가중
        self.assertIs(leases.apply(c, dp(1.49), 0.045), L)   # 두 번 적용하지 않는다

    def test_inside_debt_only_adds_interest(self):
        c = co(4.0)
        L = leases.apply(c, dp(4.29), 0.045)
        self.assertEqual(c["market"]["net_debt"], 4.0)
        self.assertAlmostEqual(L["rate_used"], 0.06)   # 공시 금리 없으면 엔진 세전 차입금리
        self.assertNotIn("pretax_kd", c)

    def test_margin_path_and_value_rise(self):
        c0, c1 = co(4.0), co(4.0)
        leases.apply(c1, dp(4.29), 0.045)
        d0 = scenarios.drivers(c0, c0["scenarios"]["base"], 0.09, 0.035)
        d1 = scenarios.drivers(c1, c1["scenarios"]["base"], 0.09, 0.035)
        for a, b in zip(d0["margin"], d1["margin"]):
            self.assertAlmostEqual(b - a, c1["lease"]["margin_add"])
        self.assertGreater(dcf.value(d1)["equity"], dcf.value(d0)["equity"])

    def test_switch_off(self):
        leases.ENABLED = False
        try:
            c = co()
            self.assertIsNone(leases.apply(c, dp(1.49), 0.045))
        finally:
            leases.ENABLED = True


if __name__ == "__main__":
    unittest.main()
