"""GitHub 사용량 95% 경보 (2026-11-08)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import github_usage as G  # noqa: E402


class TestUsage(unittest.TestCase):
    def test_measure_and_message(self):
        c = G.cfg()
        m = G.measure(c=c)
        self.assertGreaterEqual(m["runs"], 0)
        self.assertGreater(m["repo_mb"], 0)
        self.assertIn("Actions 실행 시간", G.message({**m, "actions_share": 0.96}, ["actions"], c))

    def test_threshold(self):
        c = {**G.cfg(), "alert_at": 0.95}
        self.assertEqual(c["actions_free_minutes"], 2000)


if __name__ == "__main__":
    unittest.main()
