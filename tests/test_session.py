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


class TestPriceLine(unittest.TestCase):
    RTH = at(2026, 10, 30, 1, 0)      # 미국 장중(12:00 ET)
    PRE = at(2026, 10, 29, 21, 0)     # 미국 장전(08:00 ET)
    POST = at(2026, 10, 30, 6, 0)     # 미국 장후(17:00 ET)

    def test_each_session_uses_its_own_value(self):
        d = {"change": 2.34, "premarket_change": -1.2, "postmarket_change": 5.0, "update_mode": "streaming"}
        self.assertEqual(session.reaction("NASDAQ_UCTT", d, now=self.RTH), "장중 +2.3%")
        self.assertEqual(session.reaction("NASDAQ_UCTT", d, now=self.PRE), "장전 -1.2%")
        self.assertEqual(session.reaction("NASDAQ_UCTT", d, now=self.POST), "장후 +5.0%")

    def test_delay_is_shown(self):
        d = {"change": -7.08, "update_mode": "delayed_streaming_1200"}
        self.assertEqual(session.reaction("KRX:000660", d, now=at(2026, 10, 30, 11, 0)), "장중 -7.1% (20분 지연)")

    def test_no_after_hours_value(self):
        d = {"change": -3.0, "postmarket_change": None}
        self.assertEqual(session.reaction("TSE:6702", d, now=at(2026, 10, 30, 16, 0)), "종가 -3.0%")     # 장중 발표
        self.assertEqual(session.reaction("TSE:6702", d, after_close=True, now=at(2026, 10, 30, 16, 0)), "")  # 마감 뒤 발표 — 반응 전
        self.assertEqual(session.reaction("TSE:6702", {}, now=at(2026, 10, 30, 16, 0)), "")
        self.assertEqual(session.reaction("LSE:BAB", {"change": -0.24, "postmarket_change": 0}, now=at(2026, 10, 31, 2, 0)), "종가 -0.2%")   # 런던은 시간외 없음 = 0

    def test_fiscal_key_to_tradingview(self):
        self.assertEqual(session.tv_symbol("NASDAQ_UCTT"), "NASDAQ:UCTT")
        self.assertEqual(session.tv_symbol("XKRX_009150"), "KRX:009150")
        self.assertEqual(session.tv_symbol("XJPX_6702"), "TSE:6702")
        self.assertEqual(session.tv_symbol("KRX:000660"), "KRX:000660")


if __name__ == "__main__":
    unittest.main()
