"""CFM闪存市场 웨이퍼 일별 종가(마스터 결정 2026-11-23 '개인 봇 한정')"""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import cfm_wafer  # noqa: E402
import memory_spot  # noqa: E402

PAGE = """<html><head><script>var sampleData=[{"date":"8/24","value":29}]</script></head><body>
<div>1Tb TLC 近半年价格</div><table><tr><th>日期</th><th>日低点</th><th>开盘价</th><th>收盘价</th></tr>
<tr><td>2026-11-20</td><td>29.00</td><td>29.00</td><td>29.00</td></tr>
<tr><td>2026-11-19</td><td>28.50</td><td>29.00</td><td>28.80</td></tr></table></body></html>"""


class TestParse(unittest.TestCase):
    def test_table_rows_only(self):
        self.assertEqual(cfm_wafer.parse(PAGE), [("2026-11-19", 28.5, 29.0, 28.8), ("2026-11-20", 29.0, 29.0, 29.0)])

    def test_no_table(self):
        self.assertEqual(cfm_wafer.parse("<html>登录</html>"), [])

    def test_internal_only(self):
        self.assertTrue(cfm_wafer.INTERNAL_ONLY)
        self.assertIn("radar", str(cfm_wafer.OUT))
        self.assertIn("inbox", str(cfm_wafer.OUT))   # git 제외 폴더


class TestSeries(unittest.TestCase):
    def test_half_year_history_has_no_ytd_base(self):
        rows = [{"date": d, "item": "512Gb TLC", "close": v} for d, v in (("2026-05-25", "23"), ("2026-10-27", "20"), ("2026-11-20", "20"))]
        s = cfm_wafer.series("512Gb TLC", "2026-01-01", rows)
        self.assertIsNone(s["ytd_base"])
        self.assertEqual(s["first"], (date(2026, 5, 25), 23.0))
        self.assertEqual(s["last"], (date(2026, 11, 20), 20.0))


class TestCaption(unittest.TestCase):
    def test_cfm_one_line_with_attribution(self):
        tf = {"kind": "NAND", "product": "Wafer 512Gb TLC", "last": ["2026-11-09", 14.267, "tf"], "tf_last": ["2026-11-09", 14.267],
              "chg": {"1W": -11.7, "1M": -24.2, "YTD": 4.0}, "src": "tf"}
        cf = [{"kind": "NAND", "product": f"CFM {i}", "last": ["2026-11-20", v, "cfm"], "tf_last": ["2026-11-20", v], "chg": {"1W": 0.0, "1M": m}, "src": "cfm"}
              for i, v, m in (("1Tb TLC", 29.0, 0.0), ("512Gb TLC", 20.0, -4.8))]
        with mock.patch.dict(sys.modules, {"trade_daily": None}):
            cap = memory_spot.caption({"since": "2026-01-01", "series": [tf] + cf, "missing": []})
        lines = [x for x in cap.splitlines() if "CFM" in x]
        self.assertIn("1Tb TLC $29.00(1M +0.0%) · 512Gb TLC $20.00(1M -4.8%)", lines[0])
        self.assertIn("TrendForce와 따로", lines[0])
        self.assertIn("来源：CFM闪存市场", cap)   # 약관이 요구하는 출처 표기
        self.assertNotIn("1Tb TLC: 공개 원천 없음", cap)


if __name__ == "__main__":
    unittest.main()
