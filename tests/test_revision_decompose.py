"""그림 8 분기별 주가 분해 — 분해 불가 구간을 빼지 않는다(2026-11-15 LBRT: 4개 분기 중 1개만, 그것도 리비전 −90% × 멀티플 +431%)"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import revision_view as rv  # noqa: E402


class TestDecompose(unittest.TestCase):
    def test_liberty_keeps_four_quarters(self):
        f = ROOT / "knowledge/models/companies/co-liberty/datapack.json"
        if not f.exists():
            self.skipTest("co-liberty 없음")
        dp = json.loads(f.read_text(encoding="utf-8"))
        h, px = rv.load_hist(dp["consensus"]["eps_history"]["rows"]), rv.load_prices(dp["id"])
        if not px:
            self.skipTest("시세 없음")
        dec = rv.decompose(h, dp["revision_events"], px)
        self.assertEqual(len(dec), 4)
        for x in dec:   # 적자·0 근처면 멀티플을 만들지 않는다
            if x["rev"] is None:
                self.assertIsNone(x["rerate"])
                self.assertTrue(x["why"])
            else:
                self.assertLess(abs(x["rerate"]), 3)


if __name__ == "__main__":
    unittest.main()


class TestImageTargets(unittest.TestCase):
    def test_holdings_not_drawn(self):   # LBRT '에너지 전환 지분'에 오클로 원자로가 그려졌다
        import product_images as P
        self.assertTrue(P.is_holding({"name": "에너지 전환 지분", "what": "Oklo·Fervo·Tamboran 상장 지분"}))
        self.assertFalse(P.is_holding({"name": "LPI 현장 전력", "what": "가스 왕복동 발전"}))
        self.assertTrue(P.others_only({"items": [{"this_company": False}, {"this_company": False}]}))
        self.assertFalse(P.others_only({"items": [{"this_company": False}, {"this_company": True}]}))


class TestEbitdaDecompose(unittest.TestCase):
    def test_liberty_ebitda_basis(self):   # LBRT: 기준 지표가 EBITDA — EPS 분해는 전부 불가였다
        f = ROOT / "knowledge/models/companies/co-liberty/datapack.json"
        if not f.exists():
            self.skipTest("co-liberty 없음")
        dp = json.loads(f.read_text(encoding="utf-8"))
        dec = rv.decompose_ebitda(dp, dp["revision_events"], rv.load_prices(dp["id"]))
        self.assertEqual(len(dec), 4)
        for x in dec:   # (1 + EV) = (1 + EBITDA 리비전) × (1 + 배수 변화)
            self.assertAlmostEqual(1 + x["ev"], (1 + x["rev"]) * (1 + x["rerate"]), places=6)


class TestKrActest(unittest.TestCase):
    def test_units_and_ttm_premium(self):   # 삼양식품: 억 원 실적과 십억 원 추정이 섞였고, 프리미엄이 1개 분기만
        import earnings_view
        import report_layout
        dp = {"currency_symbol": "₩", "consensus": {"surprise": [{"period": "2026Q3", "metric": "매출", "unit": "억 원", "actual": 7918, "est": 8190}],
                                                    "quarters_est": {"2026Q4": 825.0}},
              "history": {"pe_ttm": [{"date": d, "value": v} for d, v in (("2025-12-31", 23.6), ("2026-03-31", 20.7), ("2026-06-30", 17.3))]},
              "peers": [{"hist_q": [{"date": d, "pe_ttm": v} for d, v in (("2025-12-31", 15.0), ("2026-03-31", 13.0), ("2026-06-30", 12.0))]},
                        {"hist_q": [{"date": d, "pe_ttm": v} for d, v in (("2025-12-31", 17.0), ("2026-03-31", 15.0), ("2026-06-30", 14.0))]}]}
        p = report_layout.actest_chart(dp)["panels"][0]
        self.assertEqual(p["actual"][0], 791800.0)
        self.assertEqual(p["est"][1], 825000.0)
        t = earnings_view.premium_trend(dp)
        self.assertEqual(len(t[0]["values"]), 3)
        self.assertIn("후행", t[0]["metric"])

    def test_trailing_pe_adapter(self):   # 2026-11-19 BELFB: Zacks 미수록이라 대상 Fwd 이력이 비어 프리미엄이 1개 분기만 — 분기말 후행 P/E로 같은 잣대
        import importlib.util
        import tempfile
        from pathlib import Path
        spec = importlib.util.spec_from_file_location("fadapter", Path(__file__).resolve().parents[1] / "scripts" / "fiscal" / "adapter.py")
        ad = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ad)
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "knowledge" / "models" / "companies" / "x"
            d.mkdir(parents=True)
            (d / "datapack.json").write_text(json.dumps({"history": {"pe_fwd": []}, "peers": [
                {"key": "NASDAQ_A", "ticker": "A", "hist_q": [{"date": "2026-06-30", "pe_fwd": 20.0}]}, {"key": "NYSE_B", "ticker": "B"}]}), encoding="utf-8")
            ad.ROOT = Path(tmp)
            out = {"target": [{"date": "2026-03-31", "pe_ttm": 30.0}, {"date": "2026-06-30", "pe_ttm": 33.0}],
                   "peers": {"NASDAQ_A": [{"date": "2026-03-31", "pe_ttm": 20.0}, {"date": "2026-06-30", "pe_ttm": 22.0}],
                             "NYSE_B": [{"date": "2026-03-27", "pe_ttm": 30.0}, {"date": "2026-06-26", "pe_ttm": 33.0}]}}
            self.assertEqual(ad.put_trailing_pe("x", out), (2, 2))
            dp = json.loads((d / "datapack.json").read_text(encoding="utf-8"))
        self.assertEqual(dp["peers"][0]["hist_q"][1], {"date": "2026-06-30", "pe_fwd": 20.0, "pe_ttm": 22.0})   # 같은 분기말은 합친다
        import earnings_view
        t = earnings_view.premium_trend(dp)
        self.assertEqual(t[0]["peer"], [25.0, 27.5])
        self.assertEqual(t[0]["values"], [20, 20])
