"""실적 발표 알파 점검 시험 (마스터 지시 2026-11-07)"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for p in ("scripts/discovery", "scripts/portfolio", "scripts/weekly", "scripts/alpha"):
    sys.path.insert(0, str(ROOT / p))
import earnings_alpha  # noqa: E402
import earnings_sweep as es  # noqa: E402
import watchlist  # noqa: E402

PORT = """holdings:
  - id: co-old
    ticker: "OLD"
    status: 관심
# 이벤트
events: []
"""


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        p = Path(self.d.name)
        self.patches = [mock.patch.object(es, "DIR", p), mock.patch.object(es, "NAMES", p / "names.json"), mock.patch.object(es, "QUEUE", p / "q.txt"),
                        mock.patch.object(es, "known_ids", lambda: {}), mock.patch.object(watchlist, "LOG", p / "log.csv")]
        for x in self.patches:
            x.start()

    def tearDown(self):
        for x in self.patches:
            x.stop()
        self.d.cleanup()

    def rows(self, n=12):
        return [{"symbol": f"NASDAQ:T{i}", "description": f"Co {i}", "market_cap_basic": 1e9 * (i + 1), "price_free_cash_flow_ttm": 5 + i,
                 "enterprise_value_to_ebit_ttm": 4 + i, "price_book_fq": 1 + i / 5, "return_on_assets": 20 - i, "piotroski_f_score_ttm": 8,
                 "Perf.6M": i, "Perf.Y": 10 * i, "price_52_week_high": 10, "price_52_week_low": 5, "close": 6, "recommendation_total": i,
                 "eps_surprise_percent_fq": 30 - i, "revenue_surprise_percent_fq": 20 - i, "earnings_release_date": "2026-11-03"} for i in range(n)]

    def test_rank_prefers_cheap_quality_surprise(self):
        es.put("W", self.rows(), "america", total=100)
        with mock.patch("score.load_latest", lambda: ({}, {})):
            d = es.rank("W")
        self.assertEqual(d["markets"]["america"]["total"], 100)
        self.assertGreater(d["rows"]["us-t0"]["Q"], d["rows"]["us-t11"]["Q"])
        self.assertIn("us-t0", d["candidates"])

    def test_sec_and_tv_rows_merge(self):
        es.put("W", [{"symbol": "SEC:T1", "name": "T1", "rev_yoy": 0.3, "earnings_release_date": "2026-11-02"}], "america")
        es.put("W", [{"symbol": "NASDAQ:T1", "market_cap_basic": 5e9}], "america")
        r = json.loads(es.path("W").read_text(encoding="utf-8"))["rows"]["us-t1"]
        self.assertEqual(r["symbol"], "NASDAQ:T1")
        self.assertEqual(r["rev_yoy"], 0.3)

    def test_add_sweep_skips_held_and_writes_floor(self):
        port = Path(self.d.name) / "portfolio.yaml"
        port.write_text(PORT, encoding="utf-8")
        passed = [{"id": "co-old", "ticker": "OLD", "alpha": 7.5, "name": "Old"}, {"id": "us-new", "ticker": "NEW", "alpha": 6.4, "name": "New"}]
        added = watchlist.add_sweep(passed, 6.0, "earnings-sweep", "2026-W46", "2026-11-14", port)
        self.assertEqual(added, ["us-new"])
        txt = port.read_text(encoding="utf-8")
        self.assertIn("alpha_floor: 6.0", txt)
        self.assertLess(txt.index("us-new"), txt.index("events:"))

    def test_sweep_entry_removed_below_floor(self):
        c = {"add": {"alpha_min": 7.0, "composite_pct": 0.75, "buy_call_counts": True, "confirm_days": 2},
             "remove": {"use_add_criteria": True, "confirm_days": 2, "killed_immediate": True, "alpha_pct": 0.5, "composite_pct": 0.5},
             "cap": {"max_auto": 8, "replace_margin": 1.0}}
        h = [{"id": "us-new", "ticker": "NEW", "status": "관심", "added_by": "earnings-sweep", "alpha_floor": 6.0}]
        st = {}
        for day in ("2026-11-14", "2026-11-15"):
            _, drops = watchlist.decide(h, {"us-new": {"alpha": 6.5, "ticker": "NEW"}}, c, st, day)
            self.assertEqual(drops, [])   # 6.5 ≥ 6.0 — v1 문턱 7.0이 아니라 자기 문턱으로 본다
        for day in ("2026-11-16", "2026-11-17"):
            _, drops = watchlist.decide(h, {"us-new": {"alpha": 5.5, "ticker": "NEW"}}, c, st, day)
        self.assertEqual(drops[0][0], "us-new")

    def test_weekly_section(self):
        s = {"tag": "2026-W46", "floor": 6.0, "universe": {"america": 900, "japan": 120}, "pool": 800, "ranked": 600, "judged": 30,
             "passed": [{"id": "us-x", "name": "X Corp", "ticker": "X", "release": "2026-11-12", "alpha": 6.8, "alpha_q": 8.1}],
             "near": [], "watchlist_added": ["us-x"], "report_queued": ["X"]}
        d = {"_earnings_alpha": s, "earnings_alpha": {"notes": {"us-x": "수주 잔고 +40%"}}}
        md = "\n".join(earnings_alpha.md_lines(d))
        self.assertIn("Earnings 알파 점검", md)
        self.assertIn("수주 잔고 +40%", md)
        self.assertIn("미국 900", md)
        self.assertIn("<h2>Earnings 알파 점검</h2>", earnings_alpha.html_section(d))
        self.assertEqual(earnings_alpha.md_lines({}), [])


if __name__ == "__main__":
    unittest.main()
