"""피터 린치 6분류(마스터 지시 2026-11-19, ADR-048)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import lynch as L  # noqa: E402


def X(**k):
    base = {"mcap_usd": 5e9, "growth": 0.10, "industry": "electronics", "pb": None, "net_cash_usd": None, "pe": 20.0, "div_yield": 0.0,
            "op_ttm_hist": [100] * 12, "rev_ttm_hist": [1000 + i for i in range(12)], "next_eps_up": True}
    base.update(k)
    return base


class TestClassify(unittest.TestCase):
    def test_growth_bands_and_size(self):
        self.assertEqual(L.classify(X(growth=0.25))["cat"], "고성장주")
        self.assertEqual(L.classify(X(growth=0.10))["cat"], "대형우량주")
        self.assertEqual(L.classify(X(growth=0.03))["cat"], "저성장주")
        r = L.classify(X(growth=0.25, mcap_usd=80e9))
        self.assertEqual(r["size"], "대형")
        self.assertTrue(any("10배는 드물다" in a for a in r["against"]))

    def test_turnaround_asset_cyclical_order(self):
        self.assertEqual(L.classify(X(op_ttm_hist=[100] * 8 + [-5] * 4))["cat"], "회생주")
        self.assertEqual(L.classify(X(op_ttm_hist=[100] * 8 + [-5] * 4, next_eps_up=False))["cat"], "대형우량주")   # 회복 기대가 없으면 회생주가 아니다
        self.assertEqual(L.classify(X(pb=0.8))["cat"], "자산주")
        self.assertEqual(L.classify(X(pb=0.8, growth=0.30))["cat"], "고성장주")   # 고성장이면 자산주로 보지 않는다
        self.assertEqual(L.classify(X(industry="memory"))["cat"], "경기순환주")
        self.assertEqual(L.classify(X(rev_ttm_hist=[1000, 1200, 900, 950]))["cat"], "경기순환주")   # 고점 대비 25% 하락

    def test_young_company_loss_exit_is_growth(self):   # Bloom: 적자 탈출 + 매출 하락 작음 → 성장 이야기
        r = L.classify(X(growth=0.33, op_ttm_hist=[-300, -200, -100, -50, 10, 50, 90, 120, 150, 160, 170, 180], rev_ttm_hist=[100, 95, 110, 130, 150]))
        self.assertEqual(r["cat"], "고성장주")

    def test_cap_and_ratios(self):
        r = L.classify(X(growth=0.10))
        self.assertEqual(L.cap_score(6.0, r)[0], 4.9)
        self.assertEqual(L.cap_score(6.0, L.classify(X(growth=0.25)))[0], 6.0)
        r = L.classify(X(growth=0.20, pe=20.0, div_yield=0.02))
        self.assertAlmostEqual(r["lynch_ratio"], 1.1)
        self.assertAlmostEqual(r["peg"], 1.0)

    def test_from_fund_turnaround(self):
        x = L.from_fund({"eps_ttm": -0.5, "eps_fwd": 0.4, "mcap_usd": 1e9, "price": 10})
        self.assertEqual(L.classify(x)["cat"], "회생주")

    def test_pulse_line(self):
        self.assertIn("10배 경로 없음", L.pulse_line(X(growth=0.03)))
        self.assertIsNone(L.pulse_line(None))


if __name__ == "__main__":
    unittest.main()
