"""Chiip Trade 매일 아침 수출입 추이 시험 (2026-11-21)"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import trade_daily as td  # noqa: E402
import usitc_dataweb as dw  # noqa: E402

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 23, 8, 0, tzinfo=KST)
C = td.cfg()


class T(unittest.TestCase):
    def test_config_items(self):
        keys = [i["key"] for i in C["items"]]
        self.assertEqual(len(keys), len(set(keys)))
        for i in C["items"]:
            self.assertIn(i["src"], ("us", "jp"))
            self.assertTrue(i["why"] and i["route"])

    def test_pick_skips_recent(self):
        td.buzz = lambda it, days=2, now=None: 0
        first = C["items"][0]["key"]
        it, why = td.pick(C, {"sent": {first: {"date": "2026-11-22"}}}, NOW)
        self.assertNotEqual(it["key"], first)
        self.assertIn("순번", why)

    def test_pick_prefers_buzz(self):
        td.buzz = lambda it, days=2, now=None: 9 if it["key"] == "ramen_kr_us" else 0
        it, why = td.pick(C, {}, NOW)
        self.assertEqual(it["key"], "ramen_kr_us")

    def test_window_and_once_a_day(self):
        res, _ = td.run(now=NOW.replace(hour=15))
        self.assertIn("skipped", res)

    def test_summary_yoy_and_share(self):
        rows = {f"{y}-{m:02d}": {"month": f"{y}-{m:02d}", "value": 100 * (y - 2024), "world": 400, "qty": ""} for y in (2025, 2026) for m in range(1, 10)}
        lines, trend = td.summary({"src": "us", "code": "1902300060"}, rows)
        self.assertIn("전년 대비 +100%", lines[-1])
        self.assertIn("비중 50%", lines[-1])
        self.assertIn("+100%", trend)

    def test_dataweb_flatten(self):
        cols = ["HTS Number", "Year", "Country", "Description", "Quantity Description"] + dw.MONTHS
        tb = [{"columns": cols, "rows": [["1", "2026", "South Korea", "x", ""] + ["1,000"] * 12]},
              {"columns": cols, "rows": [["1", "2026", "South Korea", "x", ""] + ["10"] * 12]}]
        f = dw.flatten(tb)
        self.assertEqual(f[("South Korea", "2026-03")], [1000.0, 10.0])

    def test_dataweb_body(self):
        b = dw.body("Import", "8542320036", [2025, 2026])
        self.assertEqual(b["searchOptions"]["commodities"]["granularity"], "10")
        self.assertEqual(b["searchOptions"]["componentSettings"]["yearsTimeline"], "Monthly")


if __name__ == "__main__":
    unittest.main()
