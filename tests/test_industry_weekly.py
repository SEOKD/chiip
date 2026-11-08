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

DP = {"industry": "semiconductors.dram-hbm", "week": "2026-W46", "date": "2026-11-15", "title": "t",
      "narrative": {k: "글" for k in F.NEED_NAR} | {"summary": [["q", "a"]]},
      "segments": [{"id": "a", "name": "HBM", "market": 10.0, "expected": 18.0, "confidence": 0.7},
                   {"id": "b", "name": "범용 DRAM", "market": 5.0, "expected": 4.0, "confidence": 0.6}],
      "value_chain": [{"layer": "다이", "who": "SK하이닉스", "bottleneck": "TSV"}],
      "checkpoints": [{"date": "2026-12-01", "what": "x", "p": 0.6}, {"date": "2027-01-15", "what": "y", "p": 0.4}],
      "counter": [{"text": "반대", "source": "u"}], "sources": ["a", "b", "c"]}


class TestWeekly(unittest.TestCase):
    def test_universe_from_watchlist(self):
        m = W.members()
        self.assertIn("co-skhynix", [x["id"] for x in m["semiconductors.dram-hbm"]])   # 큰 세부 산업(반도체)은 테마로 나뉜다
        self.assertGreaterEqual(len(m["electric-utilities"]), 3)

    def test_market_taxonomy(self):
        c = W.cfg()
        self.assertGreater(len(c["industries"]), 25)   # 시장 세부 산업(GICS) 기준 — 옛 분야 모듈 11개보다 잘다
        self.assertTrue(all(len(v) >= c["min_members"] for v in c["_members"].values()))
        cls = W.classify()
        by_t = {str(m["ticker"]).split(".")[0]: m["sub"] for m in cls.values()}
        self.assertEqual(by_t["ON"], "Semiconductors")   # YAML이 ON을 참/거짓으로 읽지 않게
        ids = [m["id"] for v in c["_members"].values() for m in v]
        self.assertEqual(len(ids), len(set(ids)))   # 한 종목은 한 산업에만

    def test_recency_penalty(self):
        tmp = Path(tempfile.mkdtemp()) / "picks.csv"
        tmp.write_text("date,industry,score,rank,top3,why\n2026-11-08,semiconductors.dram-hbm,,1,,x\n", encoding="utf-8")
        orig = W.PICKS
        W.PICKS = tmp
        try:
            r = {x["industry"]: x for x in W.rank(date(2026, 11, 15))}
        finally:
            W.PICKS = orig
        self.assertIn("최근", " ".join(r["semiconductors.dram-hbm"]["notes"]))

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
