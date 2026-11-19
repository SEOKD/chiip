"""M&A 시너지 (마스터 지시 2026-11-03)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import ma_view as mv  # noqa: E402

DP = {"unit": "B$", "ma": {"deals": [{"target": "T", "closed": "2026-10-01", "price": 1.75, "target_ebitda": 0.15, "target_ni": 0.08, "premium": 0.35,
       "financing": {"debt": 1.25, "rate": 0.055}, "integration_cost": 0.06,
       "synergies": [{"type": "원가", "name": "조달", "run_rate": 0.04, "full_year": 2028, "prob": 0.8},
                     {"type": "매출", "name": "교차판매", "run_rate": 0.2, "margin": 0.3, "full_year": 2029, "prob": 0.5}]}],
       "acquirer": {"eps": 4.1, "shares": 0.162, "tax": 0.21, "year0": 2026}}}


class TestMA(unittest.TestCase):
    def test_ramp_and_full(self):
        m = mv.deal_model(DP["ma"]["deals"][0], DP["ma"]["acquirer"], 0.09)
        self.assertAlmostEqual(m["full"], 0.04 * 0.8 + 0.2 * 0.3 * 0.5)
        self.assertTrue(all(a <= b + 1e-12 for a, b in zip(m["total"], m["total"][1:])))
        self.assertLess(m["multiple_syn"], m["multiple"])
        self.assertEqual(len(m["eps"]), 4)

    def test_section(self):
        s = mv.section(DP)
        self.assertEqual(s["h2"], "M&A 시너지")
        self.assertIsNone(mv.section({"ma": {"none": "없음"}}))

    def test_one_chart_one_axis(self):   # 2026-11-19 MTZ — 램프·가치 vs 웃돈·EPS 효과를 한 그림, 인수 전 EPS 대비 %로
        charts = [b["chart"] for b in mv.section(DP)["blocks"] if b["type"] == "chart"]
        self.assertEqual(len(charts), 1)
        c = charts[0]
        self.assertEqual((c["kind"], c["unit"]), ("line", "%"))
        self.assertIn("웃돈", c["title"])
        total, parts = c["series"][0]["points"], c["series"][1:]
        for i, (_, v) in enumerate(total):   # 구성 요소 합 = EPS 효과 합계
            self.assertAlmostEqual(sum(s["points"][i][1] for s in parts), v, delta=0.3)


if __name__ == "__main__":
    unittest.main()
