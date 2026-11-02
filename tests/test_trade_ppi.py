"""무역·PPI 세부 항목 수집과 리포트 연결 (마스터 지시 2026-11-02)"""
import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "radar"), str(ROOT / "scripts" / "tenbagger"), str(ROOT / "tests")]
import input_view as iv  # noqa: E402
import trade_ppi as tp  # noqa: E402
from test_margin_supply import DP, MARGIN  # noqa: E402

DATA = {"as_of": "2026-11-02", "inputs": {
    "memory": {"name": "메모리", "hs": "854232", "proxy": ["us", "eu"], "ppi": {"us": {"period": "2026-09", "yoy": -0.02}, "jp": {"period": "2026-09", "yoy": 0.04}, "eu": {"period": "2026-08", "yoy": 0.06}},
               "trade": {"eu": {"partners": {"TW": {"value": 90, "share": 0.9, "yoy": 0.2, "period": "2026-08"}, "KR": {"value": 10, "share": 0.1, "yoy": None, "period": "2026-08"}}}}},
    "copper": {"name": "구리", "hs": "740811", "proxy": ["eu"], "ppi": {"us": None, "eu": {"period": "2026-08", "yoy": 0.2}}, "trade": {}}}}


def tagged():
    dp = copy.deepcopy(DP)
    dp["margin"]["products"][0]["bom"][0]["input"] = "memory"
    dp["supply"]["links"][0]["input"] = "memory"
    return dp


class TestParsers(unittest.TestCase):
    def test_jsonstat_months(self):
        doc = {"id": ["freq", "geo", "time"], "size": [1, 1, 3], "value": {"0": 1.5, "2": 2.5}, "dimension": {"time": {"category": {"index": {"2026-01": 0, "2026-02": 1, "2026-03": 2}}}}}
        self.assertEqual(tp.jsonstat_months(doc), {"2026-01": 1.5, "2026-03": 2.5})

    def test_jsonstat_refuses_wider_query(self):
        with self.assertRaises(ValueError):
            tp.jsonstat_months({"id": ["unit", "time"], "size": [2, 1], "value": {}, "dimension": {"time": {"category": {"index": {"2026-01": 0}}}}})

    def test_ons_months(self):
        body = json.dumps({"months": [{"date": "2026 SEP", "value": "264.3"}, {"date": "2025 SEP", "value": "200"}, {"date": "bad", "value": "1"}]})
        with mock.patch.object(tp, "get", return_value=body):
            self.assertEqual(tp.ppi_ons("EW74"), {"2026-09": 264.3, "2025-09": 200.0})

    def test_start_month(self):
        self.assertEqual(tp.start_month(date(2026, 11, 2), 30), "2024-05")


class TestMetrics(unittest.TestCase):
    def test_ppi_year_change(self):
        m = tp.ppi_metric({"2025-09": 100.0, "2026-09": 110.0})
        self.assertEqual(m["period"], "2026-09")
        self.assertAlmostEqual(m["yoy"], 0.1)

    def test_no_year_ago_is_unknown(self):
        self.assertIsNone(tp.ppi_metric({"2026-09": 110.0})["yoy"])
        self.assertIsNone(tp.ppi_metric({}))

    def test_trade_uses_three_month_sum(self):
        s = {"2025-06": 1.0, "2025-07": 1.0, "2025-08": 2.0, "2026-06": 2.0, "2026-07": 2.0, "2026-08": 4.0}
        m = tp.trade_metric(s)
        self.assertEqual(m["value"], 8.0)
        self.assertAlmostEqual(m["yoy"], 1.0)

    def test_gap_year_is_not_guessed(self):
        self.assertIsNone(tp.trade_metric({"2026-06": 1.0, "2026-07": 1.0, "2026-08": 1.0})["yoy"])


class TestRun(unittest.TestCase):
    def test_total_failure_keeps_yesterday(self):
        blank = {"a": {"name": "a", "hs": "1", "ppi": {"us": None}, "trade": {}}}
        with mock.patch.object(tp, "collect", return_value=(blank, [], ["bls: URLError"])), mock.patch.object(tp, "LATEST") as f, mock.patch.object(tp, "config", return_value={}), mock.patch.object(tp.common, "load_env", return_value={}):
            with self.assertRaises(RuntimeError):
                tp.run(date(2026, 11, 2))
            f.write_text.assert_not_called()

    def test_config_marks_every_country(self):
        cfg = tp.config()
        self.assertEqual(set(cfg["sources"]), {"us", "eu", "uk", "jp", "kr", "tw"})
        for v in cfg["sources"].values():
            self.assertEqual(set(v), {"trade", "ppi"})

    def test_job_is_scheduled(self):
        self.assertIn('"trade_ppi"', (ROOT / "radar" / "run_hourly.py").read_text(encoding="utf-8"))


class TestReport(unittest.TestCase):
    def test_exact_series_beats_broad_proxy(self):
        self.assertAlmostEqual(iv.price_move(DATA["inputs"]["memory"]), 0.04)

    def test_proxy_used_only_when_nothing_else(self):
        self.assertAlmostEqual(iv.price_move(DATA["inputs"]["copper"]), 0.2)

    def test_pressure_keeps_pass_through(self):
        drag, cover = iv.pressure(tagged(), DATA)
        self.assertAlmostEqual(drag, -(0.6 * 0.6 * 0.5) * 0.04 * 0.5)
        self.assertAlmostEqual(cover, 0.6 * 0.6 * 0.5 / 0.6)

    def test_blocks_show_proxy_mark_and_source(self):
        text = str(iv.margin_blocks(tagged(), DATA))
        self.assertIn("+6.0%*", text)
        self.assertIn("TW 90%", text)
        self.assertIn("OPM은", text)

    def test_supply_table(self):
        self.assertIn("TW 90% · KR 10%", str(iv.supply_blocks(tagged(), DATA)))

    def test_valuation_line(self):
        self.assertIn("투입 물가 점검", iv.valuation_line(tagged(), DATA)["text"])

    def test_untagged_report_stays_quiet(self):
        dp = {"margin": MARGIN, "supply": DP["supply"]}
        self.assertEqual(iv.margin_blocks(dp, DATA), [])
        self.assertEqual(iv.supply_blocks(dp, DATA), [])
        self.assertIsNone(iv.valuation_line(dp, DATA))

    def test_no_data_file_stays_quiet(self):
        self.assertEqual(iv.margin_blocks(tagged(), {}), [])

    def test_unknown_input_stops(self):
        dp = tagged()
        dp["margin"]["products"][0]["bom"][0]["input"] = "없는품목"
        with self.assertRaises(ValueError):
            iv.margin_blocks(dp, DATA)


if __name__ == "__main__":
    unittest.main()
