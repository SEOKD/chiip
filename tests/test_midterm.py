"""중간선거 사건 연구 (마스터 지시 2026-11-03)"""
import random
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar" / "markets"))
import midterm as mt  # noqa: E402

C = {"estimation": {"start": "2026-08-03", "end": "2026-10-30"}, "event_day": "2026-11-03", "window_end": "2026-11-13", "benchmark": "SPY",
     "symbols": {"sector": ["A", "B", "C"], "industry": []}, "smart_money": {"weights": {"car": 0.35, "abvol_up": 0.25, "cmf": 0.25, "rel_strength": 0.15}, "cmf_window": 10},
     "fred": {"DGS10": "10년", "VIXCLS": "VIX"}}


def series(jump, vol_up):
    random.seed(len(str(jump)) + int(vol_up * 10))
    d, px, out, mkt = date(2026, 8, 3), 100.0, [], []
    while d <= date(2026, 11, 13):
        if d.weekday() < 5:
            post = d >= date(2026, 11, 3)
            r = random.gauss(0, 0.005) + (jump if post else 0)
            px *= 1 + r
            v = 1e6 * (vol_up if post else 1)
            hi, lo = (px, px * 0.99) if post and jump > 0 else ((px * 1.01, px) if post and jump < 0 else (px * 1.003, px * 0.997))
            out.append([d.isoformat(), px, hi, lo, px, v])
        d += timedelta(days=1)
    return out


class TestStudy(unittest.TestCase):
    def test_inflow_sector_scores_highest(self):
        data = {"SPY": series(0, 1), "A": series(0.01, 2.0), "B": series(0, 1), "C": series(-0.01, 1.5)}
        r = mt.study(data, C)
        self.assertGreater(r["A"]["car"], 0.05)
        self.assertLess(r["C"]["car"], -0.05)
        self.assertEqual(max(("A", "B", "C"), key=lambda k: r[k]["smart"]), "A")
        self.assertEqual(r["A"]["days"], 9)

    def test_fred_moves_in_bp(self):
        m = mt.fred_moves({"DGS10": {"2026-11-02": 4.90, "2026-11-05": 4.80}, "VIXCLS": {"2026-11-02": 20.0, "2026-11-04": 18.0}}, C)
        self.assertAlmostEqual(m["DGS10"]["chg"], -10.0)
        self.assertAlmostEqual(m["VIXCLS"]["chg"], -0.1)


    def test_tick_reports_only_changes(self):
        import json, tempfile
        mt.DIR = Path(tempfile.mkdtemp())
        q = {s: {"change": 0.1, "relative_volume_10d_calc": 1} for s in mt.tick_symbols()}
        q["AMEX:XLV"]["change"] = 1.5
        f = mt.DIR / "q.json"
        f.write_text(json.dumps({"data": q}))
        self.assertEqual(mt.tick(f)["changes"], ["개장 첫 관측"])
        self.assertFalse(mt.tick(f)["changed"])
        q["AMEX:XLV"]["change"], q["AMEX:XLE"]["change"] = -1.5, 1.2
        f.write_text(json.dumps({"data": q}))
        self.assertTrue(mt.tick(f)["changed"])

if __name__ == "__main__":
    unittest.main()
