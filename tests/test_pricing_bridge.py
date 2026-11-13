"""원가·판매가 물가 다리(ADR-031, 마스터 지시 2026-11-13)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import input_view as iv  # noqa: E402

HIST = {"inputs": {"power": {"ppi": {"us": {"2025-10": 100.0, "2026-04": 105.0, "2026-07": 108.0, "2026-10": 110.0}}}}}
CPI = {"raw": {"CUUR0000SERF01": {"2025-09": 100.0, "2026-09": 103.0, "2026-10": 104.0}}}   # 2025-10 없음
DP = {"margin": {"costs": [{"name": "전력", "stage": "매출원가", "pct_rev": 0.10, "input": "power"},
                           {"name": "인건비", "stage": "매출원가", "pct_rev": 0.30}]},
      "pricing": [{"business": "회비", "index": "cpi:CUUR0000SERF01", "label": "클럽 CPI", "company": {"yoy": 0.12}}]}


class TestBridge(unittest.TestCase):
    def test_cost_change_and_margin_hit(self):
        b = iv.bridge(DP, HIST, CPI)
        r = b["costs"][0]
        self.assertAlmostEqual(r["ch12"], 0.10)
        self.assertAlmostEqual(r["ch3"], 110 / 108 - 1)
        self.assertAlmostEqual(r["d_gpm"], -0.01)   # 10% 비용 × +10% 물가, 전가 0%
        self.assertEqual(b["unmapped"], ["인건비"])

    def test_price_index_falls_back_to_month_with_pair(self):
        p = iv.price_rows(DP, HIST, CPI)[0]
        self.assertEqual(p["month"], "2026-09")
        self.assertAlmostEqual(p["idx12"], 0.03)
        self.assertAlmostEqual(p["power"], 0.09)

    def test_blocks_flag_spread_and_show_unmapped(self):
        B = iv.pricing_blocks(DP, HIST, CPI)
        self.assertEqual(B[0]["type"], "hl")   # 격차 3% − 10% = −7%p → 강조 한 줄
        text = " ".join(str(b.get("text", "")) for b in B)
        self.assertIn("인건비", text)
        self.assertIn("9.0%p 더 올랐다", text)
        self.assertTrue(any(b.get("type") == "chart" for b in B))

    def test_nothing_without_material(self):
        self.assertEqual(iv.pricing_blocks({"margin": {"costs": []}}, HIST, CPI), [])


if __name__ == "__main__":
    unittest.main()
