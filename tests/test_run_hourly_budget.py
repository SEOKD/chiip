"""run_hourly 시간 예산·밀린 순서(2026-11-11 실시간 점검) — 끝쪽 작업이 굶지 않는다"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import run_hourly  # noqa: E402
from pollers import common  # noqa: E402


class T(unittest.TestCase):
    def test_overdue_first(self):
        now = common.now_kst()
        last = {"a": common.iso(now - timedelta(minutes=40)), "b": common.iso(now - timedelta(days=10))}
        with mock.patch.object(common, "load_state", return_value=last):
            self.assertGreater(run_hourly.overdue("b", 1440), run_hourly.overdue("a", 30))
            self.assertEqual(run_hourly.overdue("never", 60), 1e9)

    def test_budget_stops_new_jobs(self):
        jobs = [("j1", "m", 30), ("j2", "m", 30)]
        clock = iter([0, 0, run_hourly.BUDGET_MIN * 60 + 1])
        with mock.patch.object(run_hourly, "JOBS", jobs), mock.patch.object(common, "is_due", return_value=True), \
                mock.patch.object(common, "stay_awake"), mock.patch.object(run_hourly, "overdue", return_value=1), \
                mock.patch("time.monotonic", side_effect=lambda: next(clock)), \
                mock.patch.object(run_hourly, "run_child", return_value=False) as rc:
            run_hourly.main([])
        self.assertEqual([c.args[0] for c in rc.call_args_list], ["j1"])


if __name__ == "__main__":
    unittest.main()
