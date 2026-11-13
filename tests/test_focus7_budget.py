"""@focus7 회차 시간 상한·돌아가며 시작(2026-11-13 점검: 182회 연속 12분 초과)"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import common, rss  # noqa: E402


class TestBudget(unittest.TestCase):
    def setUp(self):
        self.state = {}
        self.p = [mock.patch.object(common, "load_state", lambda n, d=None: self.state.get(n, d if d is not None else {})),
                  mock.patch.object(common, "save_state", lambda n, v: self.state.__setitem__(n, v)),
                  mock.patch.object(rss, "feed_urls", lambda src: iter([("@focus7", [f"c{i}"]) for i in range(6)]))]
        for x in self.p:
            x.start()
        self.seen = []

    def tearDown(self):
        for x in self.p:
            x.stop()

    def run_once(self, budget, clock):
        def entries(names, stats=None, window="1d"):
            self.seen.append(names[0])
            return []
        with mock.patch.object(rss, "focus7_entries", entries), mock.patch.object(rss, "FOCUS7_BUDGET_S", budget), \
             mock.patch("time.monotonic", clock):
            rss.poll_source({"id": "src-news7-focus"})

    def test_stops_at_budget_and_resumes_next_run(self):
        t = iter([0, 0, 10, 20, 30, 999, 999, 999, 999])   # 시작 0 → 세 묶음 뒤 상한 초과
        self.run_once(25, lambda: next(t))
        self.assertEqual(self.seen, ["c0", "c1", "c2"])
        st = self.state["focus7_stats"]
        self.assertEqual(st["src-news7-focus"]["deferred"], 3)
        self.assertEqual(st["cursor"]["src-news7-focus"], 3)
        self.assertNotIn("src-news7-focus", st.get("sweep", {}))   # 덜 돈 쓸어 담기는 끝난 것으로 치지 않는다
        self.seen = []
        self.run_once(10 ** 6, lambda: 0)
        self.assertEqual(self.seen, ["c3", "c4", "c5", "c0", "c1", "c2"])


if __name__ == "__main__":
    unittest.main()
