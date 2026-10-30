"""어닝콜 인사이트 피드 계산 — 반응 세션·반응일 AR·β·발표 전 상승·표류(마스터 지시 2026-10-30)"""
import random
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "insight"))

import call_feed as cf  # noqa: E402


def _data(jump_day=None, jump=0.10):
    random.seed(1)
    d, rows, mk, px = date(2026, 4, 1), [], {}, 100.0
    while d <= date(2026, 10, 29):
        if d.weekday() < 5:
            m = random.gauss(0, 0.01)
            r = 1.5 * m + random.gauss(0, 0.005) + (jump if d.isoformat() == jump_day else 0)
            px *= 1 + r
            rows.append([d.isoformat(), px])
            mk[d.isoformat()] = m
        d += timedelta(days=1)
    return {"stock": rows, "mkt_ret": mk, "peer_ret": {}, "call": {"answer_words_avg": 150}, "prev_call": {"answer_words_avg": 200}}


class TestCallFeed(unittest.TestCase):
    def test_prev_event(self):
        self.assertEqual(cf.prev_event("q1-2027"), "q4-2026")
        self.assertEqual(cf.prev_event("q3-2026"), "q2-2026")

    def test_session_rules(self):
        dates = ["2026-10-27", "2026-10-28", "2026-10-29"]
        self.assertEqual(cf.reaction_day("NASDAQ_X", datetime(2026, 10, 27, 20, 30, tzinfo=timezone.utc), dates)[:2], ("2026-10-28", "2026-10-27"))   # 16:30 EDT 장 마감 후
        self.assertEqual(cf.reaction_day("NASDAQ_X", datetime(2026, 10, 28, 11, 0, tzinfo=timezone.utc), dates)[:2], ("2026-10-28", "2026-10-27"))    # 장 전
        self.assertEqual(cf._offset("NYSE", datetime(2026, 11, 5, tzinfo=timezone.utc))[0], -5)   # 11월 첫 일요일 뒤 EST

    def test_reaction_ar_and_drift(self):
        o = cf.calc(_data("2026-10-28"), "NASDAQ_T", "q1-2027", {"ticker": "T", "utc": "2026-10-27T20:30:00+00:00", "lag_h": 5})
        self.assertEqual(o["reaction_day"], "2026-10-28")
        self.assertAlmostEqual(o["reaction"]["beta"], 1.5, delta=0.15)
        self.assertGreater(o["reaction"]["ar_pct"], 8)
        self.assertEqual(o["drift"]["days"], 1)
        self.assertEqual(o["qa"]["answer_len_change_pct"], -25.0)

    def test_no_reaction_session_yet(self):
        o = cf.calc(_data(), "NASDAQ_T", "q1-2027", {"ticker": "T", "utc": "2026-10-29T20:30:00+00:00", "lag_h": 3})
        self.assertIsNone(o["reaction"])
        self.assertEqual(o["base_day"], "2026-10-29")
        self.assertIn("runup_20d", o)


if __name__ == "__main__":
    unittest.main()
