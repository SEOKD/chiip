"""CFTC COT 지표 — 순포지션·백분위·극단 이름(2026-11-09)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import cftc as C  # noqa: E402


def rows(nets, oi=1000):
    return [{"report_date_as_yyyy_mm_dd": f"2026-01-{i + 1:02d}", "asset_mgr_positions_long": str(max(n, 0)), "asset_mgr_positions_short": str(max(-n, 0)),
             "open_interest_all": str(oi)} for i, n in enumerate(nets)]


class TestCOT(unittest.TestCase):
    def test_stats(self):
        s = C.stats(rows(list(range(-10, 10)) + [50]), "asset_mgr", [5, 95])
        self.assertEqual((s["net"], s["chg_w"], s["pct_oi"]), (50, 41, 5.0))
        self.assertGreaterEqual(s["pctile"], 95)
        self.assertTrue(s["extreme"].startswith("롱 극단"))

    def test_sign_aware_names(self):
        self.assertTrue(C._ext(-8912, 100, [5, 95]).startswith("숏 축소"))   # 순숏인데 3년 중 가장 덜 숏
        self.assertTrue(C._ext(4035, 4, [5, 95]).startswith("롱 축소"))
        self.assertIsNone(C._ext(100, 50, [5, 95]))

    def test_short_history_skipped(self):
        self.assertIsNone(C.stats(rows([1, 2, 3]), "asset_mgr", [5, 95]))


if __name__ == "__main__":
    unittest.main()
