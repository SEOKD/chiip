"""밸류에이션 엔진 시험 — 가상 데이터(합성, 실제 종목 수치 아님)로 계산식을 검증한다."""
import csv
import math
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "valuation"))

import engine  # noqa: E402
from markets import valuation_data as vd  # noqa: E402
from pollers import common  # noqa: E402


class TestEngineMath(unittest.TestCase):
    def test_ntm_weighting(self):
        row = {"eps_fy0": "10", "eps_fy1": "20", "fy0_end": "2026-12-31"}
        # 2026-10-28 기준 회계연도 말까지 64일 → FY0 가중 64/365
        w = 64 / 365
        self.assertAlmostEqual(engine.ntm(row, "2026-10-28"), w * 10 + (1 - w) * 20, places=6)
        self.assertEqual(engine.ntm({"eps_fy1": "5"}, "2026-10-28"), 5.0)

    def test_ols_recovers_coefficients(self):
        X = [[1.0, float(i), float(i % 3)] for i in range(20)]
        y = [2.0 + 0.5 * x[1] - 1.5 * x[2] for x in X]
        beta = engine.ols(X, y, ridge=0)
        for b, t in zip(beta, (2.0, 0.5, -1.5)):
            self.assertAlmostEqual(b, t, places=6)

    def test_pct_rank_and_change(self):
        self.assertEqual(engine.pct_rank({"a": 1, "b": 3, "c": 2}), {"a": 0.0, "c": 50.0, "b": 100.0})
        self.assertAlmostEqual(engine.pct_change(110, 100), 0.10)
        self.assertAlmostEqual(engine.pct_change(-5, -10), 0.5)  # 적자 축소는 개선(+)


class TestEngineCompute(unittest.TestCase):
    """유니버스 전체에 합성 스냅숏·가격을 만들어 compute() 전 과정을 돌린다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.saved = {k: getattr(engine, k) for k in ("VAL", "SNAP_DIR", "PRICE_DIR", "HIST_DIR", "SCEN")}
        engine.VAL, engine.SNAP_DIR, engine.PRICE_DIR = t, t / "snapshots", t / "prices"
        engine.HIST_DIR, engine.SCEN = t / "history", t / "scenarios.csv"
        engine.SNAP_DIR.mkdir()
        engine.PRICE_DIR.mkdir()
        self.cfg = common.load_yaml("config/valuation.yaml")
        self.asof = common.now_kst().date()
        rows = []
        for i, u in enumerate(self.cfg["universe"]):
            if not u.get("code"):
                continue
            eps0, eps1 = 2.0 + i % 7, (2.0 + i % 7) * (1.05 + (i % 5) * 0.08)
            price_now = eps1 * (12 + (i % 9) * 3)
            rows.append({"date": self.asof.isoformat(), "id": u["id"], "code": u["code"], "region": u["region"],
                         "sub": u["sub"], "price": price_now, "price_date": self.asof.isoformat(),
                         "fy0_end": (self.asof + timedelta(days=60)).isoformat(),
                         "eps_fy0": eps0, "eps_fy1": eps1, "eps_fy1_lo": eps1 * 0.9, "eps_fy1_hi": eps1 * 1.1,
                         "eps_fy0_30d": eps0, "eps_fy1_30d": eps1 / (1 + (i % 4) * 0.02),
                         "eps_fy0_90d": eps0 * 0.95, "eps_fy1_90d": eps1 / (1 + (i % 6) * 0.04),
                         "rev_fy0": 100, "rev_fy1": 100 * (1.1 + (i % 3) * 0.1), "op_margin": 0.1 + (i % 5) * 0.08,
                         "up30": i % 5, "down30": (i + 2) % 4, "beat_drop4": (i % 3) / 2})
            with (engine.PRICE_DIR / f"{u['code']}.csv").open("w", encoding="utf-8", newline="") as f:
                w = csv.writer(f)
                w.writerow(["date", "close"])
                for d in range(400, -1, -1):
                    day = self.asof - timedelta(days=d)
                    w.writerow([day.isoformat(), price_now / (1 + (i % 8) * 0.05) ** (d / 90)])
        self.rows = rows
        with (engine.SNAP_DIR / f"{self.asof:%Y%m%d}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=vd.SNAP_COLS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        nv = next(r for r in rows if r["id"] == "co-nvidia")
        with engine.SCEN.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["as_of", "id", "scenario", "metric", "value", "multiple", "prob"])
            w.writerow(["2026-10-28", "co-nvidia", "bear", "PRICE", nv["price"] * 0.5, "", 0.25])
            w.writerow(["2026-10-28", "co-nvidia", "base", "PRICE", nv["price"], "", 0.5])
            w.writerow(["2026-10-28", "co-nvidia", "bull", "PRICE", nv["price"] * 1.5, "", 0.25])

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(engine, k, v)
        self.tmp.cleanup()

    def test_full_compute(self):
        n = engine.compute()
        self.assertGreater(n, 50)
        res = engine.load_latest()
        self.assertEqual(res["regression"]["status"], "ok")
        rows = {r["id"]: r for r in res["rows"]}
        nv = rows["co-nvidia"]
        src = next(r for r in self.rows if r["id"] == "co-nvidia")
        # 수익률 분해: ret90 = eps_chg90 + pe_chg90
        self.assertAlmostEqual(nv["ret90"], nv["eps_chg90"] + nv["pe_chg90"], places=9)
        # 역DCF 식 재현
        r, n_y, tpe = 0.09, self.cfg["params"]["horizon_years"], self.cfg["subsectors"]["accelerator"]["terminal_pe"]
        g = (src["price"] * (1 + r) ** n_y / (nv["eps_ntm"] * tpe)) ** (1 / (n_y - 1)) - 1
        self.assertAlmostEqual(nv["implied_growth"], g, places=9)
        # 시나리오: 주가가 약세·강세 한가운데 → 내포 강세 확률 0.5, 기대값 = 주가
        self.assertAlmostEqual(nv["implied_bull_prob"], 0.5, places=9)
        self.assertAlmostEqual(nv["scn_expected"], src["price"], places=6)
        # 반영도 지수: 0~100, 구성 요소 3개 이상일 때만
        for row in rows.values():
            if row["priced_in"] is not None:
                self.assertTrue(0 <= row["priced_in"] <= 100)
                self.assertGreaterEqual(row["priced_in_n"], 3)
        self.assertIn("반영도 지수", engine.digest("evening"))
        self.assertIn("NTM P/E", engine.card("co-skhynix"))


class TestCollectorParsing(unittest.TestCase):
    def test_parse_fundamentals_trend_and_beat_drop(self):
        d = {"General": {"CurrencyCode": "USD"},
             "Highlights": {"MarketCapitalization": 1e9, "RevenueTTM": 100, "GrossProfitTTM": 60},
             "Valuation": {"ForwardPE": "20"},
             "Earnings": {"Trend": {"2026-12-31": {"period": "0y", "date": "2026-12-31", "earningsEstimateAvg": "2"},
                                    "2027-12-31": {"period": "+1y", "date": "2027-12-31", "earningsEstimateAvg": "3",
                                                   "epsTrend30daysAgo": "2.8", "epsRevisionsUpLast30days": "4",
                                                   "epsRevisionsDownLast30days": None}},
                          "History": {"a": {"reportDate": "2026-07-30", "beforeAfterMarket": "AfterMarket",
                                            "epsActual": 1.1, "surprisePercent": 5.0}}}}
        prices = [("2026-07-29", 100.0), ("2026-07-30", 100.0), ("2026-07-31", 95.0)]
        out = vd.parse_fundamentals(d, prices)
        self.assertEqual((out["eps_fy0"], out["eps_fy1"], out["eps_fy1_30d"]), (2.0, 3.0, 2.8))
        self.assertEqual((out["up30"], out["down30"]), (4.0, 0))
        self.assertAlmostEqual(out["gross_margin"], 0.6)
        self.assertEqual(out["beat_drop4"], 1.0)  # 서프라이즈인데 다음 날 −5%

    def test_manual_fill_revisions(self):
        manual = [{"as_of": "2026-07-01", "id": "co-x", "period": "+1y", "eps_avg": "100"},
                  {"as_of": "2026-09-20", "id": "co-x", "period": "+1y", "eps_avg": "110"},
                  {"as_of": "2026-10-27", "id": "co-x", "period": "+1y", "eps_avg": "121", "fy_end": "2027-12-31"}]
        row = {"id": "co-x"}
        self.assertTrue(vd.manual_fill(row, manual, "2026-10-28"))
        self.assertEqual((row["eps_fy1"], row["eps_fy1_30d"], row["eps_fy1_90d"]), (121.0, 110.0, 100.0))

    def test_slot(self):
        cfg = {"slots": [{"name": "morning", "from": "05:30", "to": "07:30"}]}
        from datetime import datetime
        self.assertEqual(vd.in_slot(datetime(2026, 10, 28, 6, 0), cfg), "morning")
        self.assertIsNone(vd.in_slot(datetime(2026, 10, 28, 8, 0), cfg))


if __name__ == "__main__":
    unittest.main()
