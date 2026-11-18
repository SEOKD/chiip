"""2026-11-18 — TradingView 한도·막힌 종목·'성공'인데 산출물 없음(Analysis 13·18·22시 ASML 반복 실패, tv-sync 누락)"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for sub in ("scripts/ops", "scripts/fiscal", "scripts/tenbagger"):
    sys.path.insert(0, str(ROOT / sub))
import adapter  # noqa: E402
import catchup  # noqa: E402
import pick_report  # noqa: E402


class TestResilience(unittest.TestCase):
    def test_blocked_pick_is_skipped_then_expires(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(pick_report, "BLOCKED", Path(d) / "b.json"):
                pick_report.block("co-asml", "TradingView 일일 한도")
                self.assertIn("co-asml", pick_report.blocked_ids())
                self.assertNotIn("co-asml", pick_report.blocked_ids(datetime.now() + timedelta(hours=pick_report.BLOCK_HOURS + 1)))

    def test_easyconomics_daily_passes_gate_and_merges(self):
        rows = [{"date": f"2026-0{1 + i // 28}-{1 + i % 28:02d}", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1} for i in range(70)]
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(adapter, "ROOT", Path(d)):
                self.assertEqual(adapter.put_ohlcv_ec("co-x", {"data": rows}), (70, 70))
                n, k = adapter.put_ohlcv_ec("co-x", {"d": ["2026-04-01"], "o": [1], "h": [2], "l": [0.5], "c": [1.5], "v": [2]})
                self.assertEqual((n, k), (71, 1))
                head = (Path(d) / "knowledge/models/companies/co-x/ohlcv.csv").read_text(encoding="utf-8").split("\n", 1)[0]
                self.assertNotIn("근사", head)

    def test_success_without_output_is_rerun(self):
        now = catchup._dt("2026-11-18T23:55+09:00")
        doc = {"now": now.isoformat(), "tasks": [{"taskId": "chiip-tv-sync", "cronExpression": "20 6 * * *", "enabled": True, "jitterSeconds": 82,
                                                   "runs": [{"started_at": "2026-11-17T21:22:11Z", "status": "succeeded"}]}]}
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(catchup, "ROOT", Path(d)):
                out = catchup.judge(doc, {})
        self.assertEqual(out["rerun"][0]["why"], "성공 표시지만 산출물 없음")


if __name__ == "__main__":
    unittest.main()
