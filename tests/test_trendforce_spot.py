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

    def test_parse_wafer_spot_table(self):
        """IB 리포트가 그리는 NAND 웨이퍼 현물(2026-11-23) — 머리가 'Weekly High'인 'Wafer Spot Price'표도 읽는다"""
        cells = ["NAND Flash Spot Price", "Last Update 2026-11-09 14:40 (GMT+8)", "Item", "Daily High", "Daily Low", "Session High", "Session Low", "Session Average", "Session Change", "History",
                 "MLC 64Gb 8GBx8", "56.00", "41.50", "56.00", "41.50", "44.174", "▲", "0.42 %",
                 "NAND Flash Contract Price", "Last Update 2026-09-30 10:00 (GMT+8)", "Item", "High", "Low", "Average", "Average Change", "Low Change", "History",
                 "NAND 64Gb 8Gx8 MLC", "23.70", "23.30", "23.528", "▲", "0.44 %", "▲", "0.43 %",
                 "Wafer Spot Price", "Last Update 2026-11-09 14:40 (GMT+8)", "Item", "Weekly High", "Weekly Low", "Session High", "Session Low", "Session Average", "Session Change", "History",
                 "512Gb TLC", "19.00", "12.00", "19.00", "12.00", "14.267", "▼", "-11.67 %", "256Gb TLC", "20.00", "16.80", "20.00", "16.80", "18.142", "▼", "-1.21 %",
                 "Memory Card Spot Price", "Last Update 2026-11-09 14:40 (GMT+8)", "Item", "Daily High", "Daily Low", "Session High", "Session Low", "Session Average", "Session Change", "History",
                 "MicroSD 16GB", "2.70", "2.40", "2.70", "2.40", "2.525", "▼", "-2.89 %"]
        html = "<table>" + "".join(f"<tr><td>{x}</td></tr>" for x in cells) + "</table>"
        r = {x["item"]: x for x in T.parse(html)}
        self.assertEqual(sorted(r), ["MLC 64Gb 8GBx8", "Wafer 256Gb TLC", "Wafer 512Gb TLC"])   # 고정거래가·메모리카드 표는 뺀다
        self.assertEqual((r["Wafer 512Gb TLC"]["avg"], r["Wafer 512Gb TLC"]["chg"], r["Wafer 512Gb TLC"]["table"]), (14.267, -11.67, "NAND 웨이퍼"))
        self.assertEqual(r["MLC 64Gb 8GBx8"]["avg"], 44.174)
        self.assertEqual(T.NAND, "Wafer 512Gb TLC")

    def test_parse_weekly_wafer_post(self):
        txt = "Memory Price Weekly Update — NAND\n26년 11월 2일\n\n512Gb TLC $16.152🔻 YoY +252.97%⛔️\n256Gb TLC $18.365⏸️ YoY +675.55%⏸️\n128Gb TLC $9.967⏸️\n\n* 시가총액 $421.02B"
        r = T.parse_wafer_post(txt, "https://t.me/x/1")
        self.assertEqual([(x["date"], x["item"], x["avg"]) for x in r],
                         [("2026-11-02", "Wafer 512Gb TLC", 16.152), ("2026-11-02", "Wafer 256Gb TLC", 18.365), ("2026-11-02", "Wafer 128Gb TLC", 9.967)])
        self.assertTrue(all(x["updated"].endswith("00:00") and x["source"].startswith("tg:") for x in r))   # 공개 현물표 관측이 같은 날 있으면 그쪽이 이긴다
        self.assertEqual(T.parse_wafer_post("Memory Price Weekly Update — DRAM\n26년 11월 13일\nDDR5 16G: $60.233"), [])

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




class TestInsights(unittest.TestCase):
    """TrendForce 주간 인사이트 글 → 512Gb TLC 웨이퍼(2026-11-26 마스터 지시 "다른 파이프라인을 찾아라")"""
    def test_price_and_week_monday(self):
        import trendforce_spot as T
        r = T.parse_insight("<p>Spot prices of 512Gb TLC wafers dropped by 9.19% this week (October 26), with average quotations arriving at US$16.883.</p>", "2026-10-28T15:15:17")
        self.assertEqual((r["date"], r["avg"], r["chg"]), ("2026-10-26", 16.883, -9.19))

    def test_change_only_and_wrong_paren_date(self):
        import trendforce_spot as T
        r = T.parse_insight("<p>Spot prices of 512Gb TLC wafers rose 4.55% this week (November 9).</p>", "2026-11-18T10:00:00")
        self.assertEqual((r["date"], r["avg"], r["chg"]), ("2026-11-16", None, 4.55))   # 괄호 날짜가 아니라 글이 올라온 주 월요일

    def test_series_drops_typo(self):
        import trendforce_spot as T
        rows = [{"date": "2026-06-08", "item": "Wafer 512Gb TLC", "avg": "20.638", "chg": "-0.22", "source": "tf-insights"},
                {"date": "2026-06-15", "item": "Wafer 512Gb TLC", "avg": "21.431", "chg": "-1.0", "source": "tf-insights"}]   # 글의 -1.00%와 맞지 않는 값
        self.assertEqual([str(d) for d, _ in T.wafer_series(rows=rows)], ["2026-06-08"])


if __name__ == "__main__":
    unittest.main()
