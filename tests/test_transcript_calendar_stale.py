"""어닝콜 대기 — 감시 목록이 실적 일정보다 나중에 바뀌면 일정을 다시 받게 한다(2026-11-19 PANW 누락)"""
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import transcript_watch as T  # noqa: E402


class Stale(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.cal, self.watch = self.d / "cal.json", self.d / "watch.yaml"
        self.old = (T.CAL, T.WATCH)
        T.CAL, T.WATCH = self.cal, self.watch

    def tearDown(self):
        T.CAL, T.WATCH = self.old

    def test_watch_changed_after_calendar(self):
        now = datetime.now(timezone.utc)
        self.cal.write_text(json.dumps({"fetched": (now - timedelta(hours=1)).isoformat()}), encoding="utf-8")
        self.watch.write_text("x", encoding="utf-8")
        self.assertIn("감시 목록", T.calendar_stale(now))
        t = time.time() - 7200
        os.utime(self.watch, (t, t))
        self.assertIsNone(T.calendar_stale(now))
        self.assertIn("시간", T.calendar_stale(now + timedelta(hours=7)))


if __name__ == "__main__":
    unittest.main()
