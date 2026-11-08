"""run_poll — 밀린 원천부터, 원천별 프로세스·시간 한도(2026-11-09 Pulse 시의성 점검: 11개 원천이 3.5일 굶었다)"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import run_poll as R  # noqa: E402


class TestOrder(unittest.TestCase):
    def test_starved_first(self):
        now = R.common.now_kst()
        last = {"fast": (now - timedelta(minutes=10)).isoformat(), "starved": (now - timedelta(days=3)).isoformat()}
        with mock.patch.object(R.common, "load_state", return_value=last):
            srcs = [{"id": "fast", "interval_min": 5}, {"id": "starved", "interval_min": 60}, {"id": "never", "interval_min": 60}]
            order = sorted(srcs, key=lambda x: -R.overdue(x))
        self.assertEqual([x["id"] for x in order], ["never", "starved", "fast"])   # 3일(72배) 밀린 원천이 10분(2배) 지난 원천보다 먼저

    def test_budget_below_task_limit(self):
        self.assertLess(R.BUDGET_MIN + R.SOURCE_TIMEOUT_MIN / 4, 30)   # Windows 작업 30분 한도 안에서 판정·발송 시간이 남는다


if __name__ == "__main__":
    unittest.main()
