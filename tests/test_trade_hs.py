"""HS 시계열 저장소와 급등 품목 (마스터 지시 2026-11-02)"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import trade_hs as th  # noqa: E402

CFG = {"surge": {"window": 3, "min_yoy": 0.5, "top": 2, "min_value": {"us": 100.0}}}
NOW = ["2026-06", "2026-07", "2026-08"]
PREV = ["2025-06", "2025-07", "2025-08"]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.c = th.connect(Path(self.tmp.name) / "t.sqlite")
        self.addCleanup(self.c.close)

    def put(self, hs, now, prev, reporter="us"):
        th.store(self.c, [(reporter, "import", th.WORLD, hs, p, now, "USD") for p in NOW] + [(reporter, "import", th.WORLD, hs, p, prev, "USD") for p in PREV])


class TestStore(Base):
    def test_upsert_keeps_latest_revision(self):
        th.store(self.c, [("us", "import", "WORLD", "1", "2026-08", 1.0, "USD")])
        th.store(self.c, [("us", "import", "WORLD", "1", "2026-08", 2.0, "USD")])
        self.assertEqual(self.c.execute("SELECT value FROM obs").fetchall(), [(2.0,)])

    def test_months_between_crosses_year(self):
        self.assertEqual(th.months_between("2025-11", "2026-02"), ["2025-11", "2025-12", "2026-01", "2026-02"])

    def test_missing_newest_first_and_refresh(self):
        th.store(self.c, [("us", "import", "WORLD", "1", "2026-01", 1.0, "USD")])
        got = th.missing_months(self.c, "us", "import", "2025-11", "2026-03", 2)
        self.assertEqual(got, ["2026-01", "2026-02", "2026-03"])

    def test_universe_from_us_codes(self):
        th.store(self.c, [("us", "import", "WORLD", h, "2026-08", 1.0, "USD") for h in ("854232", "850423", "010121")])
        self.assertEqual(th.universe(self.c, ["8542"]), ["854232"])


class TestSurge(Base):
    def test_ranks_by_money_gained_not_percent(self):
        self.put("a", 1000, 500)
        self.put("b", 300, 100)
        self.put("c", 5000, 2000)
        self.assertEqual([r["hs"] for r in th.surge(self.c, CFG)], ["c", "a"])

    def test_small_item_is_filtered(self):
        self.put("tiny", 10, 1)
        self.assertEqual(th.surge(self.c, CFG), [])

    def test_slow_growth_is_filtered(self):
        self.put("a", 1000, 900)
        self.assertEqual(th.surge(self.c, CFG), [])

    def test_no_year_ago_is_not_a_surge(self):
        th.store(self.c, [("us", "import", th.WORLD, "new", p, 1000.0, "USD") for p in NOW])
        self.assertEqual(th.surge(self.c, CFG), [])

    def test_reporter_without_floor_is_skipped(self):
        self.put("a", 1000, 100, "xx")
        self.assertEqual(th.surge(self.c, CFG), [])


class TestParsers(unittest.TestCase):
    def test_census_month(self):
        body = json.dumps([["I_COMMODITY", "I_COMMODITY_SDESC", "GEN_VAL_MO", "COMM_LVL", "time"], ["854232", "MEMORIES", "10", "HS6", "2026-08"], ["010121", "HORSES", "0", "HS6", "2026-08"]])
        with mock.patch.object(th.tp, "get", return_value=body):
            self.assertEqual(th.census_month("import", "2026-08", "k"), ({"854232": 10.0}, {"854232": "MEMORIES", "010121": "HORSES"}))

    def test_census_month_not_published(self):
        with mock.patch.object(th.tp, "get", return_value=""):
            self.assertEqual(th.census_month("import", "2026-09", "k"), ({}, {}))

    def test_comext_two_products_two_months(self):
        doc = {"id": ["freq", "reporter", "partner", "product", "flow", "indicators", "time"], "size": [1, 1, 1, 2, 1, 1, 2], "value": {"0": 1.0, "3": 4.0},
               "dimension": {"product": {"category": {"index": {"a": 0, "b": 1}}}, "time": {"category": {"index": {"2026-07": 0, "2026-08": 1}}}}}
        with mock.patch.object(th.tp, "get", return_value=json.dumps(doc)):
            self.assertEqual(th.comext_rows(["a", "b"], "import", "2026-07"), [("a", "2026-07", 1.0), ("b", "2026-08", 4.0)])


class TestWiring(unittest.TestCase):
    def test_config_and_jobs(self):
        cfg = th.scan_config()
        self.assertTrue({"chapters", "backfill_months", "months_per_run", "surge"} <= set(cfg))
        self.assertIn('"trade_hs"', (ROOT / "radar" / "run_hourly.py").read_text(encoding="utf-8"))
        self.assertIn("trade-hs", (ROOT / "config" / "pipeline_health.yaml").read_text(encoding="utf-8"))

    def test_total_failure_raises(self):
        with mock.patch.object(th, "collect", side_effect=lambda c, cfg, t, e, err: err.append("x") or 0), mock.patch.object(th, "connect"), mock.patch.object(th, "scan_config", return_value=CFG):
            with self.assertRaises(RuntimeError):
                th.run(env={})


if __name__ == "__main__":
    unittest.main()
