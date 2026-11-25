"""Chiip Spot Report — 두 칸, 새 값이 올 때만 보고(2026-11-23 마스터 지시). DRAM은 qpx.kr RDIMM 32GB·UDIMM 16GB(2026-11-25)"""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import qpx_spot as Q  # noqa: E402
import spot_report as S  # noqa: E402


class TestSpotReport(unittest.TestCase):
    def test_window_is_12_months(self):
        self.assertEqual(S.since_day(date(2026, 11, 23)), date(2025, 11, 23))

    def test_due_only_when_a_series_moves(self):
        k = {"tf": "2026-11-16", "dx": "2026-11-23"}
        with mock.patch.object(S, "keys", return_value=k), mock.patch.object(S, "chart", return_value=("p.png", {})), \
             mock.patch.object(S.common, "load_state", return_value={"dram": dict(k), "nand": {"tf": "2026-11-16", "dx": "2026-11-20"}}), \
             mock.patch.dict(sys.modules, {"memory_spot": mock.MagicMock(), "rdimm_spot": mock.MagicMock(), "qpx_spot": mock.MagicMock()}):
            st = S.status()
        self.assertFalse(st["dram"]["due"])                       # 두 지표 모두 지난 보고와 같다
        self.assertEqual(st["nand"]["updated"], ["DRAMeXchange"])  # 한쪽만 새로 와도 보고

    def test_caption_names_both_sources(self):
        summ = {"kind": "nand", "as_of": "2026-11-23", "dx_unit": "USD", "tf_name": "512Gb TLC 웨이퍼 현물 (달러)", "dx_name": "MLC 64Gb 칩 현물",
                "trendforce": {"last": ["2026-11-16", 1865.0], "chg_1w": -4.36, "chg_1m": None},
                "dramexchange": {"last": ["2026-11-23", 61.61], "chg_1w": 0.8, "chg_1m": -0.5}}
        c = S.caption(summ)
        self.assertIn("TrendForce", c)
        self.assertIn("DRAMeXchange", c)
        self.assertNotIn("Badonions", c)
        self.assertIn("1개월 미확인", c)

    def test_dram_caption_is_two_modules_from_qpx(self):
        summ = {"kind": "dram", "as_of": "2026-11-25", "dx_unit": "USD", "tf_name": S.SPEC["dram"]["tf_name"], "dx_name": S.SPEC["dram"]["dx_name"],
                "trendforce": {"last": ["2026-11-24", 1865.0], "chg_1w": -4.4, "chg_1m": -10.0},
                "dramexchange": {"last": ["2026-11-24", 244.33], "chg_1w": -0.3, "chg_1m": 1.0}}
        c = S.caption(summ)
        self.assertIn("UDIMM 16GB", c)
        self.assertIn("qpx.kr", c)
        self.assertNotIn("DRAMeXchange", c)


class TestQpxParse(unittest.TestCase):
    def test_rows(self):
        html = ('<tr><td class="strong mono">2026-11-24</td><td class="num">2000.00</td><td class="num">1750.00</td><td class="num strong">1865.00</td>'
                '<td class="num"><span class="delta delta--down">▼<!-- --> <!-- -->-4.36<!-- -->%</span></td></tr>'
                '<tr><td class="strong mono">2026-11-23</td><td class="num">2120.00</td><td class="num">1830.00</td><td class="num strong">1950.00</td><td class="num">—</td></tr>')
        r = Q.parse(html)
        self.assertEqual([x["date"] for x in r], ["2026-11-23", "2026-11-24"])
        self.assertEqual((r[1]["avg"], r[1]["chg"], r[0]["chg"]), (1865.0, -4.36, ""))

    def test_update_throttled(self):
        with mock.patch.object(Q.common, "load_state", return_value={"at": Q.common.iso(Q.common.now_kst())}), mock.patch.object(Q.common, "http_get") as g:
            self.assertIn("skipped", Q.update())
        g.assert_not_called()


if __name__ == "__main__":
    unittest.main()
