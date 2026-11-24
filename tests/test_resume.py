"""긴 수집 작업 이어받기(2026-11-24 — trade-ppi가 25분 한도에서도 끊김, radar/resume.py)"""
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import resume  # noqa: E402
import run_hourly  # noqa: E402
from pollers import common  # noqa: E402


class TmpState(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = mock.patch.object(common, "STATE", Path(self.tmp.name))
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)


class TestCursor(TmpState):
    def test_resume_then_finish(self):
        c = resume.Cursor("job", "k1", today=date(2026, 11, 24))
        self.assertFalse(c.resumed)
        c.mark("a", {"x": 1})
        again = resume.Cursor("job", "k1", today=date(2026, 11, 25))
        self.assertTrue(again.resumed and again.done("a"))
        self.assertEqual(again.get("a"), {"x": 1})
        self.assertEqual(resume.progress("job"), 1)
        again.finish()
        self.assertEqual(resume.progress("job"), 0)
        self.assertFalse(resume.Cursor("job", "k1", today=date(2026, 11, 25)).done("a"))

    def test_new_cycle_when_key_changes_or_old(self):
        resume.Cursor("job", "k1", today=date(2026, 11, 24)).mark("a")
        self.assertFalse(resume.Cursor("job", "k2", today=date(2026, 11, 24)).done("a"))   # 설정이 바뀌면 처음부터
        resume.Cursor("job", "k1", today=date(2026, 11, 24)).mark("a")
        self.assertFalse(resume.Cursor("job", "k1", today=date(2026, 11, 26)).done("a"))   # 이틀 지나면 새 주기


class TestRunHourlyRetry(TmpState):

    def timeout_with(self, gained):
        def fake_run(*a, **k):
            if gained:
                resume.Cursor("trade_ppi", "k").mark("in-1")
            raise subprocess.TimeoutExpired("x", 1500)
        with mock.patch("subprocess.run", side_effect=fake_run), mock.patch.object(common, "record_health") as rh:
            run_hourly.run_child("trade-ppi", 1500, every=1440)
        return rh.call_args.args[2], common.load_state("last_run")["trade-ppi"]

    def test_progress_retries_in_two_hours(self):
        msg, last = self.timeout_with(True)
        self.assertIn("이어서", msg)
        wait = timedelta(minutes=1440) - (common.now_kst() - datetime.fromisoformat(last))
        self.assertAlmostEqual(wait.total_seconds() / 60, run_hourly.RETRY_MIN, delta=2)

    def test_no_progress_waits_full_interval(self):
        msg, last = self.timeout_with(False)
        self.assertIn("다음 회차에 다시", msg)
        self.assertLess((common.now_kst() - datetime.fromisoformat(last)).total_seconds(), 60)


class TestWired(unittest.TestCase):
    def test_collectors_use_cursor(self):
        for f, name in (("trade_ppi.py", '"trade_ppi"'), ("trade_hs.py", '"trade_hs"'), ("attention.py", '"attention"')):
            src = (ROOT / "radar" / f).read_text(encoding="utf-8")
            self.assertIn(f"resume.Cursor({name}", src)
            self.assertIn(".finish()", src)
        self.assertEqual(set(run_hourly.RESUMABLE) - set(run_hourly.HEAVY), set())


if __name__ == "__main__":
    unittest.main()
