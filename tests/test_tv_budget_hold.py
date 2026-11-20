"""TradingView 시간대 독점 — 토요일 아침은 Weekly 몫(2026-11-21 마스터 지시 "이번 주 Weekly에 … 주간 상승률 순위가 빠졌다")"""
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
import tv_budget as H  # noqa: E402

CFG = {"daily_budget": 70, "priority_reserve": 30, "day_start_hour": 6, "priority_tasks": [],
       "holds": [{"weekdays": [5], "from": "06:00", "until": "10:30", "only": ["chiip-weekly"]}]}


class FakeDT(datetime):
    NOW = None

    @classmethod
    def now(cls, tz=None):
        return cls.NOW


def run(task, now):
    FakeDT.NOW = now
    with tempfile.TemporaryDirectory() as d, mock.patch.object(H, "STATE", Path(d) / "s.json"), \
            mock.patch.object(H, "cfg", return_value=CFG), mock.patch.object(H, "task_of", return_value=task), \
            mock.patch.object(H, "datetime", FakeDT), mock.patch("sys.stdin", io.StringIO(json.dumps({"tool_name": "mcp-tv-run-screener", "session_id": "abc"}))), \
            mock.patch("sys.stdout", new_callable=io.StringIO) as out:
        H.main("pre")
        return out.getvalue()


class TestHold(unittest.TestCase):
    SAT = datetime(2026, 11, 21, 7, 5, tzinfo=H.KST)

    def test_other_task_denied_saturday_morning(self):
        self.assertIn("deny", run("chiip-pulse-weekend", self.SAT))

    def test_weekly_allowed(self):
        self.assertEqual(run("chiip-weekly-review", self.SAT), "")

    def test_human_session_not_blocked(self):
        self.assertEqual(run(None, self.SAT), "")

    def test_after_window_allowed(self):
        self.assertEqual(run("chiip-pulse-weekend", datetime(2026, 11, 21, 11, 0, tzinfo=H.KST)), "")


if __name__ == "__main__":
    unittest.main()


class TestMoversMerge(unittest.TestCase):
    def test_merge_keeps_other_regions(self):
        import csv as _csv
        sys.path.insert(0, str(ROOT / "radar" / "markets"))
        sys.path.insert(0, str(ROOT / "radar"))
        import weekly_movers as W
        with tempfile.TemporaryDirectory() as d:
            src1, src2 = Path(d) / "a.json", Path(d) / "b.json"
            src1.write_text(json.dumps([{"region": "US", "rank": 1, "pct_change": 10, "name_ko": "가", "desc_ko": "칩", "theme": "반도체 칩", "ticker": "A", "as_of": "2026-11-20"}]), encoding="utf-8")
            src2.write_text(json.dumps([{"region": "JP", "rank": 1, "pct_change": 9, "name_ko": "나", "desc_ko": "칩", "theme": "반도체 칩", "ticker": "B", "as_of": "2026-11-20"}]), encoding="utf-8")
            with mock.patch.object(W, "OUT_DIR", Path(d)):
                W.put(src1, "2026-W47")
                p, n = W.put(src2, "2026-W47", merge=True)
            regions = [r["region"] for r in _csv.DictReader(open(p, encoding="utf-8"))]
        self.assertEqual(sorted(regions), ["JP", "US"])
