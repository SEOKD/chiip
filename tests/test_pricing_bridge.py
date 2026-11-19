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


class TestTrendChart(unittest.TestCase):   # 2026-11-19 — 막대 대신 추이(시작 = 100), 격차를 제목에
    def test_trend_lines_and_gap(self):
        months = [f"{2024 + (i + 10) // 12}-{(i + 10) % 12 + 1:02d}" for i in range(24)]
        hist = {"inputs": {"power": {"ppi": {"us": {m: 100 + i for i, m in enumerate(months)}}}}, "us_raw": {"X1": {m: 100 + i * 0.2 for i, m in enumerate(months)}}}
        dp = {"margin": {"costs": [{"name": "전력", "stage": "매출원가", "pct_rev": 0.1, "input": "power"}]}, "pricing": [{"business": "A", "index": "ppi_id:X1"}]}
        c = iv.pricing_chart(iv.bridge(dp, hist, {}))["chart"]
        self.assertEqual(c["kind"], "line")
        self.assertEqual([s["points"][0][1] for s in c["series"][:2]], [100.0, 100.0])
        self.assertIn("마진 압박", c["title"])
        self.assertIn("미국 PPI(X1)", c["series"][1]["name"] + iv.index_name("ppi_id:X1"))

    def test_only_two_lines(self):   # 2026-11-19 MTZ — 항목별 점선 없이 원가(가중)·판매가(평균) 두 선만
        months = [f"{2024 + (i + 10) // 12}-{(i + 10) % 12 + 1:02d}" for i in range(24)]
        ser = lambda k: {m: 100 + i * k for i, m in enumerate(months)}
        hist = {"inputs": {"power": {"ppi": {"us": ser(1)}}, "steel": {"ppi": {"us": ser(2)}}}, "us_raw": {"X1": ser(0.2), "X2": ser(0.5)}}
        dp = {"margin": {"costs": [{"name": "전력", "stage": "매출원가", "pct_rev": 0.1, "input": "power"}, {"name": "철강", "stage": "매출원가", "pct_rev": 0.2, "input": "steel"}]},
              "pricing": [{"business": "A", "index": "ppi_id:X1"}, {"business": "B", "index": "ppi_id:X2"}]}
        c = iv.pricing_chart(iv.bridge(dp, hist, {}))["chart"]
        self.assertEqual(len(c["series"]), 2)
        self.assertTrue(c["series"][0]["name"].startswith("원가 물가(가중)"))
        self.assertTrue(c["series"][1]["name"].startswith("판매가 물가(평균)"))
        self.assertFalse(any(s.get("dash") for s in c["series"]))
