"""BLS PPI 발표 직후 수집·개정 기록(마스터 지시 2026-11-13 — 10월 PPI가 하루 늦게, 9월 개정은 기록 없이 덮였다)"""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import ppi_release as pr  # noqa: E402
import trade_ppi  # noqa: E402
from pollers import common  # noqa: E402

CFG = {"inputs": {"semi": {"ppi": {"us": "PCU334413334413"}}, "xfmr": {"ppi": {"us": "PCU335311335311"}}}}


class TestSchedule(unittest.TestCase):
    def test_release_time_follows_us_dst(self):
        self.assertEqual(pr.release_kst(date(2026, 11, 13)).hour, 22)   # 표준시 08:30 ET = 22:30 KST
        self.assertEqual(pr.release_kst(date(2027, 4, 14)).hour, 21)    # 서머타임 = 21:30 KST
        self.assertEqual(pr.release_kst(date(2027, 3, 12)).hour, 22)    # 3월 14일 전

    def test_window_only_after_release(self):
        with mock.patch.object(pr, "releases", lambda: [date(2026, 11, 13)]):
            self.assertIsNone(pr.window(datetime(2026, 11, 13, 22, 35, tzinfo=common.KST)))
            self.assertEqual(pr.window(datetime(2026, 11, 13, 22, 45, tzinfo=common.KST)), date(2026, 11, 13))
            self.assertIsNone(pr.window(datetime(2026, 11, 14, 2, 0, tzinfo=common.KST)))

    def test_calendar_has_releases(self):
        self.assertIn(date(2026, 12, 15), pr.releases())


class TestUpdate(unittest.TestCase):
    def setUp(self):
        d = Path(tempfile.mkdtemp())
        self.p = [mock.patch.object(trade_ppi, "HISTORY", d / "history.json"), mock.patch.object(trade_ppi, "LATEST", d / "latest.json")]
        for x in self.p:
            x.start()
        trade_ppi.HISTORY.write_text(json.dumps({"inputs": {"semi": {"ppi": {"us": {"2026-08": 28.7, "2026-09": 28.801}}}}}), encoding="utf-8")
        trade_ppi.LATEST.write_text(json.dumps({"inputs": {"semi": {"ppi": {"us": {"period": "2026-09"}}}}}), encoding="utf-8")

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_new_month_revision_and_summary(self):
        us = {"PCU334413334413": {"2025-10": 27.0, "2026-08": 28.7, "2026-09": 28.81, "2026-10": 28.852},
              "PCU335311335311": {"2026-09": 475.065, "2026-10": 483.91},
              "WPUFD4": {"2025-10": 150.5, "2026-09": 159.535, "2026-10": 160.248}}
        month, revs, text = pr.update_us(datetime(2026, 11, 13, 23, 0, tzinfo=common.KST), CFG, fetch=lambda ids: us)
        self.assertEqual(month, "2026-10")
        self.assertEqual([(r["period"], r["old"], r["new"]) for r in revs], [("2026-09", 28.801, 28.81)])
        h = json.loads(trade_ppi.HISTORY.read_text(encoding="utf-8"))
        self.assertEqual(h["revisions"][0]["old"], 28.801)
        latest = json.loads(trade_ppi.LATEST.read_text(encoding="utf-8"))
        self.assertEqual(latest["inputs"]["semi"]["ppi"]["us"]["revision"]["new"], 28.81)
        self.assertIn("10월 PPI", text)
        self.assertIn("최종 수요", text)
        self.assertIn("개정", text)
        self.assertLessEqual(text.count("다."), 3)   # 한두 문장 + 개정 한 줄(소수점은 세지 않는다)

    def test_no_new_month(self):
        us = {"PCU334413334413": {"2026-08": 28.7, "2026-09": 28.801}}
        month, revs, text = pr.update_us(datetime(2026, 11, 13, 23, 0, tzinfo=common.KST), CFG, fetch=lambda ids: us)
        self.assertIsNone(month)
        self.assertIsNone(text)


if __name__ == "__main__":
    unittest.main()
