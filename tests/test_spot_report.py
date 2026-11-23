"""Chiip Spot Report — TrendForce(위)·DRAMeXchange(아래) 두 칸, 새 값이 올 때만 보고(2026-11-23 마스터 지시)"""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import spot_report as S  # noqa: E402


class TestSpotReport(unittest.TestCase):
    def test_window_is_12_months(self):
        self.assertEqual(S.since_day(date(2026, 11, 23)), date(2025, 11, 23))

    def test_due_only_when_a_series_moves(self):
        k = {"tf": "2026-11-16", "dx": "2026-11-23"}
        with mock.patch.object(S, "keys", return_value=k), mock.patch.object(S, "chart", return_value=("p.png", {})), \
             mock.patch.object(S.common, "load_state", return_value={"dram": dict(k), "nand": {"tf": "2026-11-16", "dx": "2026-11-20"}}), \
             mock.patch.dict(sys.modules, {"memory_spot": mock.MagicMock(), "rdimm_spot": mock.MagicMock()}):
            st = S.status()
        self.assertFalse(st["dram"]["due"])                       # 두 지표 모두 지난 보고와 같다
        self.assertEqual(st["nand"]["updated"], ["DRAMeXchange"])  # 한쪽만 새로 와도 보고

    def test_caption_names_both_sources(self):
        summ = {"kind": "dram", "as_of": "2026-11-23", "dx_unit": "USD", "tf_name": "DDR5 RDIMM 32GB 모듈 현물 (달러/모듈)", "dx_name": "DDR5 16Gb 칩 현물",
                "trendforce": {"last": ["2026-11-16", 1865.0], "chg_1w": -4.36, "chg_1m": None},
                "dramexchange": {"last": ["2026-11-23", 61.61], "chg_1w": 0.8, "chg_1m": -0.5}}
        c = S.caption(summ)
        self.assertIn("TrendForce", c)
        self.assertIn("DRAMeXchange", c)
        self.assertNotIn("Badonions", c)
        self.assertIn("1개월 미확인", c)


if __name__ == "__main__":
    unittest.main()
