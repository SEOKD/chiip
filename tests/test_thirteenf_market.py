"""13F 시장 전체 순위 — 증감 셈·분할 보정·ETF 제외·발송 관문 (마스터 지시 2026-11-14, ADR-034)"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import thirteenf as tf  # noqa: E402
import thirteenf_market as M  # noqa: E402
from pollers import common  # noqa: E402


class TestMarket(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = [mock.patch.object(M, "CACHE", Path(self.tmp.name) / "c"), mock.patch.object(M, "OUT", Path(self.tmp.name) / "o"),
                  mock.patch.object(M, "MAP", Path(self.tmp.name) / "o" / "map.json")]
        for x in self.p:
            x.start()
        # 기관 1~3: 두 분기 제출 / 기관 4: 이번 분기만(신규 제출 — 증감에서 뺀다)
        M.save(2026, 2, "1", {"h": {"AAA000001": [100, "ALPHA"], "SPY000001": [10, "SPDR"], "SPL000001": [100, "SPLITCO"]}})
        M.save(2026, 3, "1", {"h": {"AAA000001": [150, "ALPHA"], "SPY000001": [20, "SPDR"], "SPL000001": [400, "SPLITCO"]}})
        M.save(2026, 2, "2", {"h": {"AAA000001": [100, "ALPHA"], "BBB000001": [50, "BETA"], "SPL000001": [100, "SPLITCO"]}})
        M.save(2026, 3, "2", {"h": {"AAA000001": [80, "ALPHA"], "SPY000001": [5, "SPDR"], "SPL000001": [400, "SPLITCO"]}})
        M.save(2026, 2, "3", {"h": {"SPL000001": [10, "SPLITCO"], "AAA000001": [1, "ALPHA"]}})
        M.save(2026, 3, "3", {"h": {"SPL000001": [40, "SPLITCO"], "AAA000001": [2, "ALPHA"]}})
        M.save(2026, 2, "4", {"h": None})
        M.save(2026, 3, "4", {"h": {"AAA000001": [5, "ALPHA"]}})

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def test_aggregate_counts_and_new_filers(self):
        agg, st = M.aggregate(2026, 3, ["1", "2", "3", "4"])
        self.assertEqual(st, {"filers": 4, "both": 3, "new_filers": 1})
        a = agg["AAA000001"]
        self.assertEqual((a["holders"], a["increased"], a["decreased"]), (4, 2, 1))   # 신규 제출 기관 4는 보유 수에만
        b = agg["BBB000001"]
        self.assertEqual((b["decreased"], b["sold_out"]), (1, 1))
        self.assertEqual(agg["SPY000001"]["new"], 1)

    def test_cusip_change_merged(self):
        data = [(str(i), {"OLD000001": [100, "OLDCO"]}, {"NEW000001": [100 + (i % 3), "NEWCO HOLDINGS"]}) for i in range(40)]
        self.assertEqual(M._successors(data), {"OLD000001": "NEW000001"})
        for i, ph, ch in data:
            M.save(2026, 2, "x" + i, {"h": ph})
            M.save(2026, 3, "x" + i, {"h": ch})
        agg, st = M.aggregate(2026, 3, ["x" + i for i, _, _ in data])
        n = agg["NEW000001"]
        self.assertEqual((n["new"], n["sold_out"]), (0, 0))   # 신규 매입·전량 매도로 부풀지 않는다
        self.assertNotIn("OLD000001", agg)
        self.assertEqual(st["cusip_changes"], [["OLD000001", "NEW000001"]])

    def test_split_adjusted(self):
        self.assertEqual(M._split([4.0] * 6), 4.0)
        self.assertEqual(M._split([1.1, 0.9, 1.3, 1.0, 1.2]), 1.0)
        with mock.patch.object(M, "_split", lambda r: 4.0):
            agg, _ = M.aggregate(2026, 3, ["1", "2", "3"])
        self.assertEqual(agg["SPL000001"]["increased"], 0)   # 1:4 분할이면 ×4는 그대로 보유

    def test_rank_excludes_etf_and_maps_ticker(self):
        cmap = {"AAA000001": {"ticker": "AAA", "type": "Common Stock", "name": "ALPHA INC"}, "SPY000001": {"ticker": "SPY", "type": "ETP", "name": "SPDR"},
                "BBB000001": {"ticker": "BBB", "type": "Common Stock"}, "SPL000001": {"ticker": None}}
        with mock.patch.object(common, "load_state", lambda n, d=None: {"filings": {"2026Q3": [["1", "a", ""], ["2", "b", ""], ["3", "c", ""], ["4", "d", ""]]}}):
            res = M.rank(2026, 3, top=5, min_holders=1, map_fn=lambda cs, m: cmap)
        tick = [r["ticker"] for r in res["buy"]]
        self.assertIn("AAA", tick)
        self.assertNotIn("SPY", tick)
        msg = tf.market_message({"quarter": "2026Q3", "round": "주"}, {"top": 5, "min_holders": 1}, res)
        self.assertIn("미국 시장 전체", msg)
        self.assertIn("AAA(ALPHA INC) 2곳", msg)
        self.assertIn("SPLITCO", msg)   # 티커를 못 찾으면 발행사 이름
        self.assertIn("ETF·펀드 제외", msg)

    def test_status_waits_for_coverage(self):
        from datetime import datetime
        cfg = {"universe": "market", "send_coverage": 0.95, "rounds": [{"name": "잠정", "offset": -2}, {"name": "주", "offset": 1}, {"name": "확정", "offset": 7}]}
        now = datetime(2026, 11, 17, 10, tzinfo=tf.KST)
        loads = {"low": {"progress": {"2026Q3": {"filers": 100, "cached": 50}}}, "high": {"progress": {"2026Q3": {"filers": 100, "cached": 99}}}}
        for k, want in (("low", False), ("high", True)):
            def fake(p, d, k=k):
                return loads[k] if str(p).endswith("thirteenf_market.json") else {}
            with mock.patch.object(tf, "cfg", lambda c=cfg: c), mock.patch.object(tf, "_load", fake):
                s = tf.status(now)
            self.assertEqual(s["due"], want)
            self.assertEqual(s["round"], "주")


if __name__ == "__main__":
    unittest.main()
