"""Chiip Flow — 장초·장마감 섹터 로테이션(마스터 지시 2026-11-08)"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar" / "markets"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import sector_flow as F  # noqa: E402

K = timezone(timedelta(hours=9))


class TestFlow(unittest.TestCase):
    def test_session_dst_holiday(self):
        s = lambda t: F.session(datetime.fromisoformat(t).replace(tzinfo=K))[0]
        self.assertEqual(s("2026-11-09T23:45"), "장초")        # 겨울 시간
        self.assertEqual(s("2026-11-10T05:50"), "장마감")
        self.assertEqual(s("2027-04-06T22:45"), "장초")        # 서머타임
        self.assertEqual(s("2026-11-26T23:45"), "장외")        # 추수감사절
        self.assertEqual(s("2026-11-28T02:45"), "장마감")      # 조기 폐장 12:45 ET
        self.assertEqual(s("2026-11-08T23:45"), "장외")        # 일요일

    def test_compute_axes_and_rank(self):
        c = F.cfg()
        q = {s: {"change": 0.0, "relative_volume_10d_calc": 1.0} for s in F.symbols(c)}
        q["NASDAQ:SMH"] = {"change": 3.0, "relative_volume_10d_calc": 2.0}
        q["AMEX:XLP"] = {"change": -2.0, "relative_volume_10d_calc": 1.0}
        r = F.compute(q, c)
        self.assertEqual(r["top"][0], "NASDAQ:SMH")
        self.assertEqual(r["bottom"][0], "AMEX:XLP")
        ax = {a["name"]: a for a in r["axes"]}
        self.assertEqual(ax["반도체 ↔ 소프트웨어"]["lean"], "반도체")
        self.assertEqual(ax["경기민감 ↔ 방어"]["lean"], "경기민감")

    def test_open_close_compare(self):
        o = {"top": ["A", "B", "C"], "bottom": ["X", "Y", "Z"], "axes": [{"name": "성장 ↔ 가치", "lean": "성장"}]}
        c = {"top": ["A", "X", "D"], "bottom": ["B", "Y", "Q"], "axes": [{"name": "성장 ↔ 가치", "lean": "가치"}]}
        r = F.compare(o, c)
        self.assertEqual(r["held"], ["A"])
        self.assertIn("B", r["flipped"])
        self.assertIn("X", r["flipped"])
        self.assertEqual(r["axes_turned"], ["성장 ↔ 가치"])


if __name__ == "__main__":
    unittest.main()
