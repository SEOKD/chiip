"""TrendForce 현물표 읽기 — 표기 통일·현물표만·같은 날 늦은 갱신·연초 기준(마스터 지시 2026-11-19). 숫자는 모두 가짜."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import trendforce_spot as T  # noqa: E402


def page(cells):
    return "".join(f"<td>{c}</td>" for c in cells)


DX = page(["DRAM Spot Price", "Last Update: Jan.5 2026 18:10 (GMT+8)", "<Price Notice>", "Item", "Daily High", "Daily Low", "Session High",
           "Session Low", "Session Average", "Session Change", "DDR5 16G (2Gx8) 4800/5600", "40.00", "20.00", "40.00", "20.00", "30.000", "2.00 %",
           "DDR4 16Gb (2Gx8)3200", "70.00", "50.00", "70.00", "50.00", "60.000", "1.00 %",
           "DRAM Contract Price", "Last Update: Dec.31 2025 17:00 (GMT+8)", "Item", "Session High", "Session Low", "Session Average",
           "DDR4 16Gb 2Gx8", "61.00", "49.00", "52.00", "4.00 %",
           "NAND Flash Spot Price", "Last Update: Dec.29 2025 14:40 (GMT+8)", "Item", "Daily High", "Daily Low", "Session High", "Session Low",
           "Session Average", "Session Change", "MLC 64Gb 8GBx8", "8.00", "6.00", "8.00", "6.00", "7.000", "1.00 %",
           "Module Spot Price", "Last Update: Dec.29 2025 14:40 (GMT+8)", "Item", "Weekly High", "Weekly Low", "DDR5 UDIMM 16GB", "1", "2", "3", "4", "5", "1 %"])
TF = page(["Last Update 2026-01-05 11:00 (GMT+8)", "Item", "Daily High", "Daily Low", "Session High", "Session Low", "Session Average", "Session Change",
           "History", "DDR5 16Gb (2Gx8) 4800/5600", "40.00", "20.00", "40.00", "20.00", "29.000", "▲", "1.00 %"])


class TrendForceSpot(unittest.TestCase):
    def test_parse_spot_tables_only(self):
        r = {(x["date"], x["item"]): x for x in T.parse(DX)}
        self.assertEqual(r[("2026-01-05", "DDR5 16Gb (2Gx8) 4800/5600")]["avg"], 30.0)
        self.assertIn(("2026-01-05", "DDR4 16Gb (2Gx8) 3200"), r)          # '(2Gx8)3200' 띄어쓰기 통일
        self.assertEqual(r[("2025-12-29", "MLC 64Gb 8GBx8")]["avg"], 7.0)
        self.assertNotIn(("2025-12-31", "DDR4 16Gb 2Gx8"), r)               # 고정거래가 표는 뺀다
        self.assertFalse(any("DIMM" in k[1] for k in r))                    # 모듈 표도 뺀다

    def test_merge_keeps_latest_update_and_series(self):
        with tempfile.TemporaryDirectory() as d:
            T.OUT, T.ROWS = Path(d), Path(d) / "rows.csv"
            T.merge([{**x, "source": "wayback:1", "url": ""} for x in T.parse(TF)])        # 11:00 장중
            T.merge([{**x, "source": "wayback:2", "url": ""} for x in T.parse(DX)])        # 18:10 마감이 이긴다
            T.merge([{**x, "source": "wayback:1", "url": ""} for x in T.parse(TF)])        # 다시 와도 마감값 유지
            self.assertEqual(T.value_on("DDR5 16Gb (2Gx8) 4800/5600", "2026-01-05"), 30.0)
            T.merge([{"date": "2026-01-20", "updated": "2026-01-20 18:10", "table": "DRAM", "item": "DDR5 16Gb (2Gx8) 4800/5600",
                      "high": 1, "low": 1, "avg": 33.0, "chg": 1, "source": "live", "url": ""},
                     {"date": "2025-12-31", "updated": "2025-12-31 18:10", "table": "DRAM", "item": "DDR5 16Gb (2Gx8) 4800/5600",
                      "high": 1, "low": 1, "avg": 25.0, "chg": 1, "source": "live", "url": ""}])
            s = T.series("DDR5 16Gb (2Gx8) 4800/5600", "2026-01-01")
            self.assertEqual(s["base"][1], 25.0)                                  # 연초 기준 = 직전 연말 관측
            self.assertAlmostEqual(s["chg"]["YTD"], 32.0)
            self.assertEqual(s["n"], 2)


if __name__ == "__main__":
    unittest.main()
