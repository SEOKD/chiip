"""Quantral → Valuation Queue 맥락 묶음(ADR-032, 2026-11-14)"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
sys.path.insert(0, str(ROOT / "radar"))
import queue_context as qc  # noqa: E402
import social_surge as ss  # noqa: E402


class TestStrip(unittest.TestCase):
    def test_only_source_type_and_detected_at(self):
        raw = [{"ticker": "AMAT", "score": {"score7d": 73, "url": "u"},
                "signals": [{"sourceType": "x", "detectedAt": "2026-11-13T00:00Z", "url": "http://x", "authorHitRate": 0.7, "authorEvaluatedCalls": 9, "sentimentScore": 0.4, "text": "본문"}],
                "recaps": [{"monthStart": "2026-10-01", "postCount": 3, "author": "a"}]}]
        out = ss.strip(raw)
        self.assertEqual(out[0]["signals"], [{"sourceType": "x", "detectedAt": "2026-11-13T00:00Z"}])
        self.assertEqual(out[0]["score"], {"score7d": 73})
        self.assertNotIn("author", out[0]["recaps"][0])


class TestContext(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        (self.d / "latest.json").write_text(json.dumps({"as_of": "2026-11-14", "rows": {"co-x": {
            "ticker": "XX", "Z": 0.2, "score": 1.0, "attention": 5.1, "alert": False, "q7": 80, "sent7": 0.1,
            "channels": {"x": {"recent_n": 3}, "reddit": {"recent_n": 0}}}}}), encoding="utf-8")
        q = self.d / "q"
        q.mkdir()
        (q / "2026-W47_data.json").write_text(json.dumps({"week": "2026-W47", "period": "11/16~11/22", "rows": [
            {"ticker": "XX", "rank": 3, "posts": 90, "rxs_share": 0.8, "stories": [{"headline": "XX beat"}]}]}), encoding="utf-8")
        (q / "2026-W47_report.json").write_text(json.dumps({"as_of": "2026-11-22", "themes": [{"name": "테마", "tickers": ["XX"]}], "notes": {}}), encoding="utf-8")
        (q / "2026-W46_data.json").write_text(json.dumps({"week": "2026-W46", "rows": [{"ticker": "YY", "rank": 1}]}), encoding="utf-8")
        (q / "2026-W46_report.json").write_text(json.dumps({"as_of": "2026-11-12 시험"}), encoding="utf-8")
        self.p = [mock.patch.object(qc, "SOC", self.d / "latest.json"), mock.patch.object(qc, "QOUT", q)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()

    def test_social_crowded_and_weekly(self):
        s = qc.social("co-x")
        self.assertTrue(s["crowded"])
        self.assertEqual(s["recent"], {"X": 3})
        w = qc.weekly("XX")
        self.assertEqual((w["rank"], w["themes"]), (3, ["테마"]))
        self.assertIsNone(qc.weekly("YY"))   # 시험본은 넣지 않는다

    def test_note_line_says_not_fundamental(self):
        with mock.patch.object(qc, "ticker_of", lambda e: "XX"):
            n = qc.note_line("co-x")
        self.assertIn("과밀", n)
        self.assertIn("3위", n)
        self.assertIn("펀더멘털이 아니다", n)

    def test_market_lines_run(self):
        out = qc.market_lines()
        self.assertTrue(out[-1].startswith("IPO 감시"))


if __name__ == "__main__":
    unittest.main()
