"""치입 인사이트 판단 계산기(scripts/insight/insight_calc.py) 시험 — 2026-10-29"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "insight"))

import insight_calc as ic  # noqa: E402


class TestInsightCalc(unittest.TestCase):
    def test_materiality(self):
        self.assertEqual(ic.materiality(75, mcap=55932)["grade"], "작음")                 # 이비덴 상향폭
        self.assertEqual(ic.materiality(828, mcap=2262)["grade"], "매우 큼")              # 루멘텀 ÷ 마벨
        self.assertEqual(ic.materiality(10, mcap=None)["points"], 1)                      # 분모 없으면 정성

    def test_bridge_and_priced(self):
        b = ic.bridge(55932, delta_op=75, tax=0.3, multiple=31.9)
        self.assertAlmostEqual(b["pct_of_mcap"], 2.99, places=1)
        p = ic.priced(-4.0, market=0.0, beta=1.0, implied=b["pct_of_mcap"])
        self.assertTrue(p["label"].startswith("역방향"))
        self.assertTrue(ic.priced(0.5, implied=3.0)["label"].startswith("덜"))
        self.assertIn("과잉", ic.priced(6.0, implied=3.0)["label"])
        self.assertGreater(ic.bridge(1000, delta_cf=100, years=4, rate=0.1)["delta_value"], 300)

    def test_breakeven_matches_cbrs_note(self):
        self.assertEqual(ic.breakeven(1142, 273)["years_undiscounted"], 4.18)
        self.assertAlmostEqual(ic.breakeven(571, 273, 0.10)["years_discounted"], 2.47, places=1)

    def test_score_and_diffusion(self):
        s = ic.score(3, 1, 2, 1)
        self.assertTrue(s["lead_with_view"] and s["prediction_required"])
        self.assertTrue(ic.score(1, 0, 0, 1)["fact_only"])
        d = ic.diffusion(["link", "afterhours"], "덜 반영(지연 가능)")
        self.assertEqual(d["points"], 2)
        self.assertEqual(ic.baserate("seo")["direction"], "negative")
        self.assertIn("known", ic.baserate("nope"))


if __name__ == "__main__":
    unittest.main()
