"""소비재 KPI 나우캐스트(scripts/discovery/consumer_nowcast.py, 설계안 C 2026-11-14) 오프라인 시험"""
import random
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "discovery"))
import consumer_nowcast as nc  # noqa: E402


def synth(strength, n_co=12, n_q=24, seed=1):
    rnd = random.Random(seed)
    obs = []
    for c in range(n_co):
        y1 = 0.1
        for q in range(n_q):
            s = rnd.gauss(0, 0.3)
            y = 0.02 + 0.6 * y1 + strength * s + rnd.gauss(0, 0.05)
            yr, mo = 2018 + q // 4, 3 * (q % 4) + 3
            obs.append({"id": f"c{c}", "period": f"{yr}-{mo:02d}-28", "y": y, "y1": y1, "wiki": s, "trade": None})
            y1 = y
    return sorted(obs, key=lambda o: o["period"])


class TestNowcast(unittest.TestCase):
    def test_ols_recovers(self):
        X = [[1, x, x * x % 3] for x in range(20)]
        y = [2 + 0.5 * r[1] - r[2] for r in X]
        a, b, c = nc.ols(X, y)
        self.assertAlmostEqual(a, 2, 6); self.assertAlmostEqual(b, 0.5, 6); self.assertAlmostEqual(c, -1, 6)

    def test_true_signal_adopted_noise_not(self):
        self.assertTrue(nc.evaluate(synth(0.3), sigs=("wiki",))["wiki"]["adopted"])
        self.assertFalse(nc.evaluate(synth(0.0), sigs=("wiki",))["wiki"]["adopted"])

    def test_walk_never_uses_future(self):
        for o, _, _ in nc.walk(synth(0.3), "wiki"):
            pass
        obs = synth(0.3)
        first = nc.walk(obs, "wiki")[0][0]
        self.assertGreaterEqual(sum(1 for x in obs if nc.qkey(x["period"]) < nc.qkey(first["period"])), nc.MIN_TRAIN)

    def test_quarters_filters_gaps(self):
        seq = [("2020-03-31", 10, ""), ("2020-06-30", 11, ""), ("2020-09-30", 12, ""), ("2020-12-31", 13, ""), ("2021-03-31", 14, ""),
               ("2021-06-30", 15, ""), ("2022-06-30", 20, "")]   # 마지막은 1년 건너뜀 → 빠진다
        qs = nc.quarters(seq)
        self.assertEqual([q["period"] for q in qs], ["2021-06-30"])
        self.assertAlmostEqual(qs[0]["y"], __import__("math").log(15 / 11))

    def test_tv_quarters_ignores_labels_but_checks(self):
        vals = [[100, None], [110, None], [120, None], [130, None], [150, 50.0], [165, 50.0]]
        rec = {"symbol": "X", "first_label": "Q4 2022", "last_label": "Q1 2024", "revenue": vals}
        got = nc.tv_quarters(rec)
        self.assertEqual([p for p, _ in got], ["2022-12-31", "2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31", "2024-03-31"])
        with self.assertRaises(ValueError):          # 개수가 라벨 범위와 다르면 받지 않는다
            nc.tv_quarters(dict(rec, last_label="Q2 2024"))
        with self.assertRaises(ValueError):          # YoY가 안 맞으면(순서 어긋남) 받지 않는다
            nc.tv_quarters(dict(rec, revenue=vals[:4] + [[150, 20.0], [165, 50.0]]))

    def test_dart_quarters_q4_from_annual(self):
        def row(fs, amt, add=None, acc="매출액"):
            return {"sj_div": "IS", "fs_div": fs, "account_nm": acc, "thstrm_amount": amt, "thstrm_add_amount": add}
        resp = {"11013": [row("CFS", "100"), row("OFS", "90")], "11012": [row("CFS", "110", "210")],
                "11014": [row("CFS", "1,200", "1,410")], "11011": [row("CFS", "2,000")]}
        got = nc.dart_quarters(lambda c, y, code: {"status": "000", "list": resp[code]}, "x", [2024])
        self.assertEqual(got, [("2024-03-31", 100.0), ("2024-06-30", 110.0), ("2024-09-30", 1200.0), ("2024-12-31", 590.0)])
        self.assertEqual(nc.dart_quarters(lambda c, y, code: {"status": "013"}, "x", [2014]), [])   # 자료 없음

    def test_months_drop_and_clip(self):
        self.assertEqual(nc.months_in(date(2026, 6, 30), date(2026, 9, 30)), ["2026-07", "2026-08", "2026-09"])
        self.assertEqual(nc.months_in(date(2026, 1, 3), date(2026, 4, 4)), ["2026-01", "2026-02", "2026-03"])
        self.assertEqual(nc.clip(5), nc.CLIP)


if __name__ == "__main__":
    unittest.main()
