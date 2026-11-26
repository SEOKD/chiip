"""수집 병렬화(2026-11-26 마스터 지시 "Pulse의 정보 전달 속도 … 속도를 높여")"""
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import run_poll as R  # noqa: E402
from pollers import common  # noqa: E402


class TestParallel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for p in (mock.patch.object(common, "STATE", Path(self.tmp.name)), mock.patch.object(R, "RUNNING", Path(self.tmp.name) / "running")):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_concurrent_mark_run_keeps_all(self):   # 여러 원천이 동시에 last_run을 써도 하나도 잃지 않는다
        ts = [threading.Thread(target=common.mark_run, args=(f"src-{i}",)) for i in range(12)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(len(common.load_state("last_run")), 12)

    def test_running_marker(self):
        self.assertFalse(R.running("src-a"))
        R.mark_running("src-a")
        self.assertTrue(R.running("src-a"))   # 다른 회차는 이 원천을 건너뛴다
        R.done_running("src-a")
        self.assertFalse(R.running("src-a"))

    def test_parallel_setting(self):
        self.assertGreaterEqual(R.PARALLEL, 4)


if __name__ == "__main__":
    unittest.main()
