"""일본 상장사 컨센서스 (마스터 지시 2026-11-02)"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))

import jp_consensus as jc  # noqa: E402

ADVANTEST = {"earnings_release_date": 1793169000, "earnings_release_next_date": 1801656000, "revenue_fq": 477727000000, "revenue_forecast_fq": 434167334857,
             "earnings_per_share_fq": 267.72, "earnings_per_share_forecast_fq": 209.20609, "revenue_forecast_next_fq": 470393693750,
             "earnings_per_share_forecast_next_fq": 249.927787, "revenue_forecast_next_fy": 1831057288333, "earnings_per_share_forecast_next_fy": 1005.203742}


def row(**kw):
    r = jc.row_of("TSE:6857", ADVANTEST, "2026-11-02")
    r.update(kw)
    return r


class TestLines(unittest.TestCase):
    def test_revenue_and_eps_with_surprise(self):
        got = jc.lines(row(), "2026-10-28")
        self.assertEqual(got[0], "- 매출 4,777억 엔 (est. 4,342억 엔, +10.0%)")
        self.assertEqual(got[1], "- EPS ¥267.72 (est. ¥209.21, +28.0%)")
        self.assertIn("다음 분기 매출 est. 4,704억 엔", got[2])

    def test_before_tradingview_updates_uses_saved_next_quarter(self):
        got = jc.lines(row(release="2026-07-29"), "2026-10-28")
        self.assertEqual(got, ["- 매출 est. 4,704억 엔", "- EPS est. ¥249.93"])

    def test_one_off_eps_is_left_out(self):
        got = jc.lines(row(eps="204.02", eps_est="68.24"), "2026-10-28")
        self.assertFalse([x for x in got if x.startswith("- EPS")])

    def test_empty_cells_make_no_lines(self):
        self.assertEqual(jc.lines(row(revenue_est="", eps_est="", next_revenue="", next_eps=""), "2026-10-28"), [])

    def test_guidance_against_consensus(self):
        got = jc.lines(row(next_revenue="2829286"), "2026-10-28", 25000)
        self.assertEqual(got[-1], "- 다음 분기 매출 가이던스 2조 5,000억 엔 (est. 2조 8,293억 엔, -11.6%)")


class TestTargets(unittest.TestCase):
    CUR = {"1111": {"release": "2026-10-30", "next_release": "2027-02-01"}, "2222": {"release": "2026-08-01", "next_release": "2026-11-04"},
           "3333": {"release": "2026-08-01", "next_release": "2026-11-20"}}

    def test_only_near_earnings(self):
        got = jc.targets(date(2026, 11, 2), ["1111", "2222", "3333", "4444"], self.CUR)
        self.assertEqual(got["batches"], [["TSE:1111", "TSE:2222", "TSE:4444"]])

    def test_sunday_refreshes_all(self):
        got = jc.targets(date(2026, 11, 8), [str(1000 + i) for i in range(60)], {})
        self.assertEqual([len(b) for b in got["batches"]], [50, 10])


class TestStore(unittest.TestCase):
    def test_saves_only_changes(self):
        with tempfile.TemporaryDirectory() as d:
            store, p = Path(d) / "c.csv", Path(d) / "out.json"
            p.write_text(json.dumps({"data": {"TSE:6857": ADVANTEST}}), encoding="utf-8")
            self.assertEqual(jc.put([p], date(2026, 11, 2), store), 1)
            self.assertEqual(jc.put([p], date(2026, 11, 3), store), 0)
            p.write_text(json.dumps({"data": {"TSE:6857": dict(ADVANTEST, revenue_forecast_next_fq=480000000000)}}), encoding="utf-8")
            self.assertEqual(jc.put([p], date(2026, 11, 4), store), 1)
            self.assertEqual(len(jc.read(store)), 2)

    def test_coverage(self):
        got = jc.coverage({"a": row(), "b": row(revenue_est="", eps_est="")})
        self.assertEqual((got["companies"], got["revenue_est"], got["eps_est"]), (2, 1, 1))


if __name__ == "__main__":
    unittest.main()
