"""Chiip Industry Quarterly — 산업별 80% 관문·장부 계산·관문 (ADR-018, 2026-11-08)"""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "industry"))
import industry_quarter as IQ  # noqa: E402
import quarter_frame as QF  # noqa: E402


class TestQuarterly(unittest.TestCase):
    def setUp(self):
        self._b = IQ.BASE
        IQ.BASE = Path(tempfile.mkdtemp())

    def tearDown(self):
        IQ.BASE = self._b

    def test_season_quarter(self):
        self.assertEqual(IQ.season_quarter(date(2026, 11, 8))[0], "2026Q3")
        self.assertEqual(IQ.season_quarter(date(2027, 2, 1))[0], "2026Q4")

    def test_put_and_progress(self):
        f = IQ.BASE / "o.json"
        f.write_text(json.dumps([{"key": "NASDAQ_MU", "currency": "USD",
                                  "q": [{"period": "2026-09-03", "rev": 54.2, "gp": 47.0}, {"period": "2026-05-28", "rev": 41.5}, {"period": "2026-02-26", "rev": 23.9},
                                        {"period": "2025-11-27", "rev": 13.6}, {"period": "2025-08-28", "rev": 11.3, "gp": 5.05}],
                                  "inv": [{"period": "2026-09-03", "inventory": 10.4}, {"period": "2026-05-28", "inventory": 8.6}], "capex": [], "next_q": {"rev": 63.1}}]), encoding="utf-8")
        self.assertEqual(IQ.put("nand-storage", f, "2026Q3"), 1)
        share, n, tot, _ = IQ.progress("nand-storage", "2026Q3")
        self.assertEqual(n, 1)
        self.assertLess(share, 0.8)
        rows = {r["id"]: r for r in QF.member_rows("2026Q3", "nand-storage")}
        mu = rows["co-micron"]
        self.assertAlmostEqual(mu["rev_yoy"], 54.2 / 11.3 - 1, places=4)
        self.assertAlmostEqual(mu["gpm_chg"], 47.0 / 54.2 - 5.05 / 11.3, places=4)
        self.assertAlmostEqual(mu["inv_qoq"], 10.4 / 8.6 - 1, places=4)

    def test_gate_needs_reported_share(self):
        bad = QF.gate({"narrative": {}}, [{"reported": False}, {"reported": True}, {"reported": False}], IQ.cfg())
        self.assertTrue(any("발표 종목" in b for b in bad))

    def test_status_window(self):
        self.assertFalse(IQ.status(datetime(2026, 10, 5, 9, tzinfo=IQ.KST))["due"])   # 분기 말 + 14일 전


if __name__ == "__main__":
    unittest.main()
