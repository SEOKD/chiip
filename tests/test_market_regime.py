"""Chiip Portfolio 시장 국면·오버행 시험 (마스터 지시 2026-10-30)"""
import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))

import market_regime as mr  # noqa: E402
import overhang  # noqa: E402

RULES = {"sentiment_up": 0.05, "sentiment_down": -0.05, "fundamental_up": 0.02, "fundamental_down": -0.02}


class TestMacro(unittest.TestCase):
    def test_fred_skips_blank(self):
        self.assertEqual(mr.parse_fred("d,v\n2026-10-01,4.1\n2026-10-02,\n2026-10-03,."), [("2026-10-01", 4.1)])

    def test_describe_rate_and_index(self):
        rows = [(f"d{i}", 4.0 + i * 0.05) for i in range(25)]
        d = mr.describe(rows, "rate")
        self.assertAlmostEqual(d["d5"], 0.25)
        self.assertNotIn("pct5", d)
        d = mr.describe([(f"d{i}", 100.0 - i) for i in range(25)], "index")
        self.assertAlmostEqual(d["dd"], 76 / 100 - 1)

    def test_alert_text_in_bp_and_percent(self):
        m = {"us10y": {"d5": 0.30}, "vix": {"last": 26.0, "pct5": 0.1}, "ndx": {"pct20": -0.08}}
        rules = [{"key": "us10y", "field": "d5", "abs": 0.25, "text": "10년물 {v:+.0f}bp"}, {"key": "vix", "field": "last", "ge": 25, "text": "VIX {v:.1f}"},
                 {"key": "vix", "field": "pct5", "abs": 0.3, "text": "x"}, {"key": "ndx", "field": "pct20", "le": -0.07, "text": "나스닥 {v:+.1%}"}]
        self.assertEqual([a["text"] for a in mr.check_alerts(m, rules)], ["10년물 +30bp", "VIX 26.0", "나스닥 -8.0%"])


class TestSector(unittest.TestCase):
    def test_quadrants(self):
        self.assertIn("디레이팅", mr.quadrant(-0.1, 0.05, RULES)["label"])
        self.assertIn("동행", mr.quadrant(0.1, 0.05, RULES)["label"])
        self.assertIn("기대 선행", mr.quadrant(0.1, -0.05, RULES)["label"])
        self.assertIn("함께 약세", mr.quadrant(-0.1, -0.05, RULES)["label"])
        self.assertEqual(mr.quadrant(None, 0.05, RULES)["sentiment"], "미확인")

    def test_classify_uses_median(self):
        c = {"sectors": {"a": {"name": "A", "keys": ["K1", "K2", "K3"]}, "b": {"name": "B", "keys": ["X"]}}, "sector_rules": RULES}
        rows = [{"key": "K1", "r20": -0.2, "rev30": 0.04, "above50": False}, {"key": "K2", "r20": -0.1, "rev30": 0.03, "above50": False}, {"key": "K3", "r20": 0.0, "rev30": 0.05, "above50": True}]
        out = mr.classify(rows, c)
        self.assertAlmostEqual(out["a"]["r20"], -0.1)
        self.assertIn("디레이팅", out["a"]["label"])
        self.assertAlmostEqual(out["a"]["above50"], 1 / 3)
        self.assertEqual(out["a"]["worst"], "K1")
        self.assertEqual(out["b"]["label"], "미확인")

    def test_template_gets_keys(self):
        code = mr.sector_code()
        self.assertIn("NYSE_GEV", code)
        self.assertNotIn("__KEYS__", code)


class TestBeta(unittest.TestCase):
    def test_slope_recovers_known_beta(self):
        days = [f"2026-{m:02d}-{d:02d}" for m in range(1, 7) for d in range(1, 16)]
        idx, px = [], []
        a, b = 100.0, 50.0
        for i, d in enumerate(days):
            r = 0.01 if i % 3 else -0.012
            a *= 1 + r
            b *= 1 + 2 * r
            idx.append((d, a))
            px.append((d, b))
        slope, n = mr.beta(px, idx)
        self.assertAlmostEqual(slope, 2.0, places=6)
        self.assertGreaterEqual(n, 60)

    def test_too_few_days_is_unknown(self):
        self.assertIsNone(mr.beta([("a", 1.0), ("b", 1.1)], [("a", 1.0), ("b", 1.2)])[0])


class TestOverhang(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(overhang, "BOOK", Path(self.tmp.name) / "o.csv")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        self.tmp.cleanup()

    def test_supply_filings(self):
        for f in ("S-1", "S-3ASR", "424B5", "144", "SC 13D/A"):
            self.assertTrue(overhang.is_supply_filing(f))
        self.assertTrue(overhang.is_supply_filing("8-K", "3.02,9.01"))
        self.assertFalse(overhang.is_supply_filing("8-K", "2.02"))
        self.assertFalse(overhang.is_supply_filing("10-Q"))

    def test_put_replaces_same_item_and_needs_source(self):
        overhang.put("eroc", ["kind=락업", "date=2026-12-07", "source=u", "shares_m=10"], date(2026, 10, 30))
        overhang.put("EROC", ["kind=락업", "date=2026-12-07", "source=u", "shares_m=12"], date(2026, 10, 31))
        self.assertEqual([r["shares_m"] for r in overhang.rows()], ["12"])
        with self.assertRaises(SystemExit):
            overhang.put("EROC", ["kind=ATM"])

    def test_table_sizes_supply(self):
        overhang.put("AAA", ["kind=락업", "date=2026-11-10", "shares_m=10", "source=u"], date(2026, 10, 30))
        hs = [{"ticker": "AAA", "id": "x"}, {"ticker": "BBB", "id": "y"}]
        with mock.patch.object(overhang, "shares_and_adv", return_value=(100.0, 2.0)):
            t = overhang.table(hs, date(2026, 10, 30), {"soon_days": 30, "heavy_pct": 0.05})
        r = t["rows"][0]
        self.assertAlmostEqual(r["pct_shares"], 0.10)
        self.assertAlmostEqual(r["adv_days"], 5.0)
        self.assertTrue(r["soon"] and r["heavy"])
        self.assertEqual(t["unchecked"], ["BBB"])


if __name__ == "__main__":
    unittest.main()
