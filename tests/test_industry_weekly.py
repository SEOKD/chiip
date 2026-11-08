"""Chiip Industry Weekly — 선정 체계·조립 관문 (마스터 지시 2026-11-08)"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "industry"))
import weekly_pick as W  # noqa: E402
import weekly_frame as F  # noqa: E402

DP = {"industry": "dram-hbm", "week": "2026-W46", "date": "2026-11-15", "title": "t",
      "narrative": {k: "글" for k in F.NEED_NAR} | {"summary": [["q", "a"]]},
      "segments": [{"id": "a", "name": "HBM", "market": 10.0, "expected": 18.0, "confidence": 0.7},
                   {"id": "b", "name": "범용 DRAM", "market": 5.0, "expected": 4.0, "confidence": 0.6}],
      "value_chain": [{"layer": "다이", "who": "SK하이닉스", "bottleneck": "TSV"}],
      "checkpoints": [{"date": "2026-12-01", "what": "x", "p": 0.6}, {"date": "2027-01-15", "what": "y", "p": 0.4}],
      "counter": [{"text": "반대", "source": "u"}], "sources": ["a", "b", "c"]}


class TestWeekly(unittest.TestCase):
    def test_universe_from_watchlist(self):
        m = W.members()
        self.assertIn("co-skhynix", [x["id"] for x in m["dram-hbm"]])
        self.assertGreaterEqual(len(m["power-infra"]), 3)   # 알파 유니버스 sub 라벨까지

    def test_recency_penalty(self):
        tmp = Path(tempfile.mkdtemp()) / "picks.csv"
        tmp.write_text("date,industry,score,rank,top3,why\n2026-11-08,dram-hbm,,1,,x\n", encoding="utf-8")
        orig = W.PICKS
        W.PICKS = tmp
        try:
            r = {x["industry"]: x for x in W.rank(date(2026, 11, 15))}
        finally:
            W.PICKS = orig
        self.assertIn("최근", " ".join(r["dram-hbm"]["notes"]))

    def test_choose_outside_top3_refused(self):
        bottom = W.rank()[-1]["industry"]
        with self.assertRaises(SystemExit):
            W.choose(bottom)

    def test_gate_and_ratings(self):
        self.assertTrue(F.gate({**DP, "sources": ["a"]}))
        rows = F.rows_of(DP, F.E.config())
        self.assertEqual(rows[0]["rating"], "Attractive")   # 갭 +8%p, 확신도 0.7
        self.assertEqual(rows[1]["rating"], "In-Line")


if __name__ == "__main__":
    unittest.main()
