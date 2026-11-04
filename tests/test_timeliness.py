"""Pulse 시의성 개선 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import run_poll  # noqa: E402
import pulse  # noqa: E402
import pulse_trigger  # noqa: E402
from pollers import edgar_current  # noqa: E402

KST = timezone(timedelta(hours=9))


class T(unittest.TestCase):
    def test_fast_interval_hot_windows(self):
        self.assertEqual(run_poll.fast_interval(datetime(2026, 11, 4, 21, 0)), 2)
        self.assertEqual(run_poll.fast_interval(datetime(2026, 11, 4, 6, 30)), 2)
        self.assertEqual(run_poll.fast_interval(datetime(2026, 11, 4, 12, 0)), 5)

    def test_edgar_hits_only_watched_new(self):
        xml = ('<entry><title>8-K - NVIDIA CORP (0001045810) (Filer)</title><link href="https://sec/a"/></entry>'
               '<entry><title>8-K - OTHER INC (0000000001) (Filer)</title><link href="https://sec/b"/></entry>')
        self.assertEqual(edgar_current.hits([xml], {"1045810"}, set()), ["https://sec/a"])
        self.assertEqual(edgar_current.hits([xml], {"1045810"}, {"https://sec/a"}), [])

    def test_urgent_gate(self):
        c = {"urgent": {"enabled": True, "classes": ["실적", "공시"], "min_score": 8, "max_age_min": 30}}
        now = datetime(2026, 11, 4, 22, 0, tzinfo=KST)
        pulse.LAST_PEEK = [{"source_class": "공시", "score": 8, "published_at": "2026-11-04T21:50:00+09:00"}]
        self.assertTrue(pulse_trigger.urgent(c, now))
        pulse.LAST_PEEK = [{"source_class": "공시", "score": 6, "published_at": "2026-11-04T21:50:00+09:00"},
                           {"source_class": "방위", "score": 9, "published_at": "2026-11-04T21:50:00+09:00"},
                           {"source_class": "실적", "score": 12, "published_at": "2026-11-04T20:00:00+09:00"}]
        self.assertFalse(pulse_trigger.urgent(c, now))


if __name__ == "__main__":
    unittest.main()
