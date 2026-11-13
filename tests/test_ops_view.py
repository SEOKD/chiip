"""운영 지표 3종 + 사업별 매출 vs 물가(마스터 지시 2026-11-14, ADR-033)"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
sys.path.insert(0, str(ROOT / "radar"))
import input_view as iv  # noqa: E402
import ops_view as ov  # noqa: E402
import options_implied as oi  # noqa: E402

P = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"]


class TestRule40(unittest.TestCase):
    def test_growth_plus_fcf_and_sbc(self):
        q = [{"period": p, "rev": 100 if i < 5 else 120} for i, p in enumerate(P)]
        ops = [{"period": p, "ocf": 30, "capex": -6} for p in P]
        dp = {"industry": "software", "quarters_hist": {"q": q}, "ops": {"q": ops}, "sbc_pct_rev": 0.10}
        r = ov.rule40(dp)[-1]
        self.assertAlmostEqual(r["growth"], 0.2)
        self.assertAlmostEqual(r["fcf_margin"], 96 / 480)
        self.assertAlmostEqual(r["r40"], 40.0)
        self.assertAlmostEqual(r["r40_sbc"], 30.0)
        self.assertIn("통과", ov.rule40_blocks(dp)[0]["text"])
        self.assertEqual(ov.rule40_blocks({**dp, "industry": "semis"}), [])   # 소프트웨어만


class TestCycle(unittest.TestCase):
    def test_quadrant(self):
        c = {"bb_line": 1.0, "inv_gap": 0.05}
        self.assertIn("하향 경고", ov.quadrant({"bb4": 0.9, "inv_yoy": 0.3, "rev_yoy": 0.05}, c))
        self.assertIn("상향 국면", ov.quadrant({"bb4": 1.2, "inv_yoy": 0.05, "rev_yoy": 0.1}, c))
        self.assertIsNone(ov.quadrant({"bb4": None, "inv_yoy": 0.1, "rev_yoy": 0.1}, c))

    def test_section_from_ops_only(self):
        rows = [{"period": p, "rev": 100, "cogs": 60, "inventory": 50 + 5 * i, "orders": 130} for i, p in enumerate(P)]
        s = ov.cycle_section({"ops": {"q": rows, "orders_label": "Total Orders"}})
        self.assertIn("1.30", s["blocks"][0]["text"])
        self.assertEqual(ov.cycle_section({"ops": {"q": [{"period": p, "rev": 1} for p in P]}}), None)   # 재고 없으면 절 없음


class TestImplied(unittest.TestCase):
    def test_parse_atm_straddle_after_earnings(self):
        doc = {"timestamp": "2026-11-13 16:00:00", "data": {"current_price": 100.0, "options": [
            {"option": "XYZ261114C00100000", "bid": 9, "ask": 9},
            {"option": "XYZ261121C00100000", "bid": 4.9, "ask": 5.1, "iv": 0.8}, {"option": "XYZ261121P00100000", "bid": 4.8, "ask": 5.2, "iv": 0.9},
            {"option": "XYZ261121C00105000", "bid": 2, "ask": 2.2}, {"option": "XYZ261121P00105000", "bid": 7, "ask": 7.2}]}}
        r = oi.parse(doc, "2026-11-17", "after")
        self.assertEqual((r["expiry"], r["strike"], r["straddle"]), ("2026-11-21", 100.0, 10.0))
        self.assertAlmostEqual(r["iv"], 0.85)

    def test_blocks_compare_with_history(self):
        dp = {"options_implied": {"spot": 100, "straddle": 12, "expiry": "2026-11-21", "as_of": "2026-11-13"}}
        with mock.patch.object(ov, "earnings_moves", lambda d: [{"date": "2026-08-01", "q": "2Q", "move": 0.05}, {"date": "2026-05-01", "q": "1Q", "move": -0.05}]):
            B = ov.implied_blocks(dp)
        self.assertIn("2.4배", B[0]["text"])
        self.assertIn("큰 움직임", B[0]["text"])


class TestSegmentVsPrice(unittest.TestCase):
    def test_real_growth(self):
        segs = {"회원 회비·가입비": [{"period": "2025-09-30", "rev": 100.0}, {"period": "2025-12-31", "rev": 101.0}, {"period": "2026-03-31", "rev": 103.0},
                                   {"period": "2026-06-30", "rev": 106.0}, {"period": "2026-09-30", "rev": 110.0}]}
        dp = {"segments_hist": {"segments": segs}, "pricing": [{"business": "회원 회비", "index": "cpi:X", "label": "클럽 CPI"}]}
        cpi = {"raw": {"X": {"2025-09": 100.0, "2026-09": 105.0}}}
        r = iv.segment_rows(dp, {}, cpi)[0]
        self.assertAlmostEqual(r["nominal"], 0.10)
        self.assertAlmostEqual(r["real"], 1.10 / 1.05 - 1)
        text, chart = iv.segment_blocks([r])
        self.assertIn("실질 +4.8%", text)
        self.assertEqual(len(chart["chart"]["rows"][0]["bars"]), 3)


if __name__ == "__main__":
    unittest.main()
