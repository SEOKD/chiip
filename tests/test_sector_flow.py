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


class TestEasyconomicsFallback(unittest.TestCase):
    """TradingView 한도 때 대체 시세(2026-11-21 마스터 지시 "요새 왜 Flow 안 가져다주나?")"""

    def _files(self, d, at):
        import json as _j
        rows = [{"symbol": "SPY", "change": -1.5, "rel_volume": 1.2, "price": 600}, {"symbol": "SMH", "change": -10.6, "rel_volume": 2.75, "price": 400.06}]
        p = Path(d) / "ec.json"
        p.write_text(_j.dumps({"data": {"quote_as_of": at, "rows": rows}}), encoding="utf-8")
        return [p]

    def test_fresh_quotes_map_to_symbols(self):
        import tempfile
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as d:
            q, at, why = F.from_easyconomics(self._files(d, "2026-11-20T20:50:00+00:00"), now=datetime(2026, 11, 20, 21, 0, tzinfo=timezone.utc))
        self.assertEqual(q["NASDAQ:SMH"]["change"], -10.6)
        self.assertEqual(q["AMEX:SPY"]["relative_volume_10d_calc"], 1.2)
        self.assertEqual(why, "")

    def test_stale_quotes_rejected(self):
        import tempfile
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as d:
            q, at, why = F.from_easyconomics(self._files(d, "2026-11-19T21:00:00+00:00"), now=datetime(2026, 11, 20, 14, 50, tzinfo=timezone.utc))
        self.assertEqual(q, {})
        self.assertIn("쓰지 않음", why)
