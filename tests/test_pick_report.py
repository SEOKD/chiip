"""리포트 대기열 수동 지시 (마스터 지시 2026-11-02)"""
import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import pick_report as pr  # noqa: E402


class TestQueue(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        self.queue, self.log = d / "q.txt", d / "log.csv"
        with self.log.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=pr.FIELDS)
            w.writeheader()
            w.writerow({"date": "2026-10-30", "id": "co-ttm", "ticker": "TTMI", "html": "x", "view": "v"})
        for name, value in (("QUEUE", self.queue), ("LOG", self.log)):
            p = mock.patch.object(pr, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(pr, "_universe", lambda: {"co-ttm": {"id": "co-ttm", "name": "TTM", "ticker": "TTMI"}})
        p.start()
        self.addCleanup(p.stop)

    def pick(self, text):
        self.queue.write_text(text, encoding="utf-8")
        return pr.pick(date(2026, 11, 2))

    def test_forced_line_passes_repeat_rule(self):
        got = self.pick("TTMI | reissue | 20261030_TTMI\n")
        self.assertEqual((got["id"], got["mode"], got["note"]), ("co-ttm", "reissue", "20261030_TTMI"))

    def test_plain_line_keeps_repeat_rule(self):
        got = self.pick("TTMI\nco-new\n")
        self.assertEqual(got["id"], "co-new")
        self.assertNotIn("mode", got)

    def test_unknown_ticker_gets_us_id(self):
        got = self.pick("SDRL | new | \n")
        self.assertEqual((got["id"], got["ticker"]), ("us-sdrl", "SDRL"))

    def test_done_removes_forced_line(self):
        self.queue.write_text("TTMI | reissue | 20261030_TTMI\nORCL | new | 메모\n", encoding="utf-8")
        pr.done("co-ttm", "TTMI", "x.html", "판단", date(2026, 11, 2))
        self.assertEqual(self.queue.read_text(encoding="utf-8"), "ORCL | new | 메모\n")


if __name__ == "__main__":
    unittest.main()
