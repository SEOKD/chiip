"""Chiip Portfolio(radar/portfolio.py) 결정론 관문 오프라인 시험 — 마스터 지시 2026-10-29"""
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))

import portfolio  # noqa: E402

KST = timezone(timedelta(hours=9))


class TestPortfolio(unittest.TestCase):
    def test_sec_score_ranks_earnings_first(self):
        self.assertEqual(portfolio.sec_score("8-K", "2.02,7.01,9.01"), 10)
        self.assertEqual(portfolio.sec_score("8-K", "1.01,9.01"), 8)
        self.assertEqual(portfolio.sec_score("10-Q", ""), 6)
        self.assertLess(portfolio.sec_score("425", ""), portfolio.sec_score("4", ""))   # 스팩 홍보물은 가장 낮게

    def test_ape_signal_needs_volume_and_jump(self):
        self.assertIsNotNone(portfolio.ape_signal("MRVL", {"mentions": 18, "mentions_24h_ago": 1, "rank": 30, "rank_24h_ago": 281}))
        self.assertIsNone(portfolio.ape_signal("PWR", {"mentions": 1, "mentions_24h_ago": 1}))       # 적은 언급은 잡음
        self.assertIsNone(portfolio.ape_signal("X", {"mentions": 40, "mentions_24h_ago": 20}))       # 2배는 급증 아님

    def test_wiki_signal(self):
        base = [(f"202610{d:02d}", 100) for d in range(1, 29)]
        sig, info = portfolio.wiki_signal(base + [("20261029", 450)])
        self.assertIn("4.5배", sig)
        self.assertIsNone(portfolio.wiki_signal(base + [("20261029", 250)])[0])
        self.assertIsNone(portfolio.wiki_signal(base[:3])[0])   # 이력 부족

    def test_due_events_once(self):
        evs = [{"date": "2026-11-02", "ticker": "CCXI", "what": "임시주총", "source": "u", "confirmed": True},
               {"date": "2026-11-12", "ticker": "EROC", "what": "실적", "source": "u", "confirmed": False}]
        with mock.patch.object(portfolio, "events", return_value=evs):
            st = {}
            got = portfolio.due_events(date(2026, 11, 1), st)
            self.assertEqual([g["title"] for g in got], ["[내일] 임시주총"])
            st["events_sent"] = [g["id"] for g in got]
            self.assertEqual(portfolio.due_events(date(2026, 11, 1), st), [])          # 같은 알림은 한 번만
            self.assertEqual(portfolio.due_events(date(2026, 11, 2), st)[0]["title"], "[오늘] 임시주총")
            self.assertIn("미확정", portfolio.due_events(date(2026, 11, 12), st)[0]["title"])
            self.assertEqual(len(portfolio.upcoming(date(2026, 10, 30))), 2)

    def test_daily_tue_to_sat_once(self):
        self.assertTrue(portfolio.is_daily(datetime(2026, 10, 29, 7, 35, tzinfo=KST), {}))       # 목
        self.assertFalse(portfolio.is_daily(datetime(2026, 10, 29, 6, 35, tzinfo=KST), {}))      # 07시 전
        self.assertFalse(portfolio.is_daily(datetime(2026, 11, 1, 7, 35, tzinfo=KST), {}))       # 일(미국 토요일 장 없음)
        self.assertFalse(portfolio.is_daily(datetime(2026, 10, 29, 9, 35, tzinfo=KST), {"daily_day": "2026-10-29"}))

    def test_record_diff(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(portfolio, "COVERAGE", Path(d) / "c.csv"):
            prev, diff = portfolio.record("eroc", ["price=9.0", "target_mean=22.33", "buy=9"], date(2026, 10, 29))
            self.assertIsNone(prev)
            prev, diff = portfolio.record("EROC", ["price=9.9", "target_mean=20", "buy=9", "rec=buy"], date(2026, 10, 30))
            self.assertEqual(prev["date"], "2026-10-29")
            self.assertIn("target_mean 22.33→20 (-10.4%)", diff)
            self.assertFalse(any(x.startswith("buy") for x in diff))   # 그대로인 값은 빼고
            with self.assertRaises(SystemExit):
                portfolio.record("EROC", ["targetprice=1"])


if __name__ == "__main__":
    unittest.main()
