"""Chiip Quantral 내러티브 근거 관문(2026-11-15 마스터 지시 "X, 서브스택, 레딧의 글을 최대한 참조해 내러티브를 설명")"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "quantral"))
import weekly as Q  # noqa: E402

D = {"rows": [{"ticker": "NVDA", "stories": [{"id": 1}]}, {"ticker": "AMD", "stories": [{"id": 1}, {"id": 2}]}],
     "reads": {"1": {"X": 150, "Reddit": 40, "pages_done": True}, "2": {"X": 30, "Substack": 2, "pages_done": True}}}
P = [{"channel": "X", "stance": "약세", "gist": "a", "story": 1}, {"channel": "Reddit", "stance": "강세", "gist": "b", "story": 1},
     {"channel": "X", "stance": "중립", "gist": "c", "story": 1}]


class TestEvidence(unittest.TestCase):
    def test_pass(self):
        rp = {"themes": [{"name": "t", "tickers": ["NVDA", "AMD"], "basis": [1], "points": P}], "notes": {"NVDA": {"basis": [1], "points": P}}}
        self.assertEqual(Q.evidence_gate(D, rp), [])

    def test_stray_ticker_and_missing_channel(self):
        rp = {"themes": [{"name": "t", "tickers": ["NVDA", "AVGO"], "basis": [1], "points": P}],
              "notes": {"AMD": {"basis": [2], "points": [dict(p, story=2) for p in P]}}}
        bad = " ".join(Q.evidence_gate(D, rp))
        self.assertIn("AVGO", bad)
        self.assertIn("Substack", bad)        # 읽은 글에 Substack이 있는데 논지에 없다
        self.assertIn("Reddit", bad)          # 이야기 2엔 Reddit 글이 없다

    def test_unread_and_one_sided(self):
        d = dict(D, reads={"1": {"X": 20}})
        rp = {"notes": {"NVDA": {"basis": [1], "points": [dict(p, stance="강세", channel="X") for p in P]}}}
        bad = " ".join(Q.evidence_gate(d, rp))
        self.assertIn("멈췄다", bad)
        self.assertIn("한쪽", bad)


if __name__ == "__main__":
    unittest.main()
