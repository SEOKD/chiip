"""실적 지표 주가 줄의 장중·장전·장후 판정 시험(2026-10-30)"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar" / "markets"))

import session  # noqa: E402

KST = timezone(timedelta(hours=9))


def at(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=KST)


class TestSession(unittest.TestCase):
    def test_us_summer_time(self):
        self.assertEqual(session.label("NASDAQ_UCTT", at(2026, 10, 29, 22, 29))[0], "장전")   # 09:29 ET
        self.assertEqual(session.label("NYSE_PWR", at(2026, 10, 29, 22, 30))[0], "장중")
        self.assertEqual(session.label("NASDAQ_UCTT", at(2026, 10, 30, 5, 1))[0], "장후")      # 16:01 ET

    def test_us_winter_time(self):
        self.assertEqual(session.label("NASDAQ_UCTT", at(2026, 12, 1, 23, 29))[0], "장전")     # 09:29 EST
        self.assertEqual(session.label("NASDAQ_UCTT", at(2026, 12, 1, 23, 30))[0], "장중")
        self.assertEqual(session.label("NASDAQ_UCTT", at(2026, 11, 1, 23, 30))[0], "장후")     # 일요일 — 전환일부터 겨울 시간

    def test_korea_japan_and_weekend(self):
        self.assertEqual(session.label("XKRX_009150", at(2026, 10, 30, 8, 59))[0], "장전")
        self.assertEqual(session.label("XKRX_009150", at(2026, 10, 30, 15, 29))[0], "장중")
        self.assertEqual(session.label("XJPX", at(2026, 10, 30, 15, 30))[0], "장후")
        self.assertEqual(session.label("XKRX_009150", at(2026, 10, 31, 11, 0))[0], "장후")     # 토요일

    def test_europe_and_unknown(self):
        self.assertEqual(session.label("XETR_PRY", at(2026, 7, 1, 16, 0))[0], "장중")          # 09:00 CEST
        self.assertEqual(session.label("XLON_X", at(2026, 12, 1, 16, 59))[0], "장전")          # 07:59 GMT
        with self.assertRaises(ValueError):
            session.label("OTC_X")


if __name__ == "__main__":
    unittest.main()
