"""원가·판매가 물가 다리(ADR-031, 마스터 지시 2026-11-13)"""
import sys
import unittest
import unittest.mock
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
        self.assertIn("인건비", text)   # 미연결 항목
        self.assertIn("9.0%p 더 올랐다", text)
        self.assertTrue(any(b.get("type") == "chart" for b in B))

    def test_nothing_without_material(self):
        self.assertEqual(iv.pricing_blocks({"margin": {"costs": []}}, HIST, CPI), [])


class TestOneTable(unittest.TestCase):
    def test_margin_blocks_single_table_and_paragraph(self):
        dp = {**DP, "margin": {**DP["margin"], "products": [{"name": "p", "bom": [{"item": "전력", "input": "power"}]}]}}
        data = {"as_of": "2026-11-13", "inputs": {"power": {"ppi": {"us": {"yoy": 0.1, "period": "2026-10"}}, "proxy": []}}}
        with unittest.mock.patch.object(iv.margin_view, "compute", lambda d: {"items": [], "now": {"gpm": 0.5}}):
            B = iv.margin_blocks(dp, data, HIST, CPI)
        self.assertEqual(sum(1 for b in B if b["type"] == "table"), 1)
        self.assertEqual(sum(1 for b in B if b["type"] == "p"), 1)
        t = next(b for b in B if b["type"] == "table")
        self.assertIn("미국 3개월", t["headers"])
        self.assertEqual(t["rows"][0][4], "-1.0%p")
        self.assertEqual(len(t["headers"]), 5)   # 해외 값이 모두 미확인이면 열을 숨긴다


if __name__ == "__main__":
    unittest.main()
