"""밸류에이션 v2 1단계 엔진 오프라인 시험 (docs/valuation/v2_architecture.md)"""
import copy
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))

import dcf  # noqa: E402
import montecarlo  # noqa: E402
import pie  # noqa: E402
import regime  # noqa: E402
import upside  # noqa: E402
import wacc  # noqa: E402


def base_drivers(**kw):
    d = {"rev0": 100.0, "growth": dcf.path_linear(0.20, 0.04, 10), "margin": dcf.margin_path(0.15, 0.20, 3, 10, 0.16, 0.38),
         "tax": 0.25, "s2c": 2.0, "ic0": 60.0, "wacc": 0.09, "g_term": 0.03, "ronic": None, "net_debt": 10.0, "shares": 5.0}
    d.update(kw)
    return d


class TestDCF(unittest.TestCase):
    def test_economic_profit_identity(self):
        for kw in ({}, {"ronic": 0.15}, {"wacc": 0.12, "s2c": 1.2}):
            v = dcf.value(base_drivers(**kw))
            self.assertLess(v["ep_gap"], 1e-9)          # EP 모델 = DCF (McKinsey 항등)

    def test_value_driver_cv_equals_gordon_on_consistent_fcf(self):
        d = base_drivers(ronic=0.15)
        rows, _ = dcf.project(d)
        g, w = d["g_term"], d["wacc"]
        nopat1 = rows[-1]["nopat"] * (1 + g)
        fcf1 = nopat1 * (1 - g / 0.15)                   # 재투자 = g/RONIC × NOPAT
        self.assertAlmostEqual(nopat1 * (1 - g / 0.15) / (w - g), fcf1 / (w - g))

    def test_ronic_equal_wacc_growth_adds_no_value(self):
        # RONIC = WACC면 계속가치 = NOPAT_{T+1} / WACC — 추가 성장이 가치를 만들지 않는다(McKinsey)
        d = base_drivers(g_term=0.04)
        v = dcf.value(d)
        rows = v["rows"]
        pv_fcf = sum(r["fcff"] / (1 + d["wacc"]) ** r["t"] for r in rows)
        cv = (v["ev"] - pv_fcf) * (1 + d["wacc"]) ** len(rows)
        self.assertAlmostEqual(cv, rows[-1]["nopat"] * 1.04 / d["wacc"], places=6)

    def test_midyear_and_margin_fade(self):
        d = base_drivers()
        self.assertAlmostEqual(dcf.value(d, midyear=True)["ev"] / dcf.value(d)["ev"], 1.09 ** 0.5)
        path = dcf.margin_path(0.10, 0.30, 2, 30, lr=0.15, lam=0.38)
        self.assertAlmostEqual(path[1], 0.30)
        self.assertAlmostEqual(path[-1], 0.15, places=3)  # 장기 마진으로 수렴

    def test_rate_sensitivity_negative(self):
        rs = dcf.rate_sensitivity(base_drivers())
        self.assertLess(rs["chg"], 0)
        self.assertGreater(rs["duration"], 0)

    def test_equity_at_consistency(self):
        d = base_drivers()
        e5 = dcf.equity_at(d, 5)
        # 5년 뒤 가치를 지금으로 할인하고 그 사이 FCFF(부채 상환분)를 더하면 지금 가치와 같아야 한다(연말 할인)
        rows, _ = dcf.project(d)
        pv_fcf = sum(r["fcff"] / (1 + d["wacc"]) ** r["t"] for r in rows[:5])
        ev_now = dcf.value(d)["ev"]
        ev5 = e5 + d["net_debt"] - sum(r["fcff"] for r in rows[:5])
        self.assertAlmostEqual(ev_now, pv_fcf + ev5 / (1 + d["wacc"]) ** 5, places=6)


class TestPIEAndMC(unittest.TestCase):
    def test_implied_growth_round_trip(self):
        d = base_drivers()
        target = dcf.value(d)["equity"]
        k, c = pie.implied_growth(d, target)
        self.assertAlmostEqual(k, 1.0, places=4)
        self.assertAlmostEqual(c, pie.cagr(d), places=6)

    def test_higher_target_needs_more_growth(self):
        d = base_drivers()
        v = dcf.value(d)["equity"]
        _, c1 = pie.implied_growth(d, v)
        _, c2 = pie.implied_growth(d, 2 * v, year=5)
        self.assertGreater(c2, c1)

    def test_mc_reproducible_and_scenario_mix(self):
        co = {"rev0": 100.0, "tax": 0.25, "ic0": 60.0, "horizon": 10, "market": {"net_debt": 10.0, "shares": 5.0},
              "scenarios": {"bull": {"prob": 0.3, "growth": {"start": 0.3, "end": 0.04}, "margin": {"m0": 0.15, "target": 0.22, "lr": 0.18, "lam": 0.3}, "s2c": 2.0},
                            "bear": {"prob": 0.7, "growth": [0.0, -0.1, 0.05], "margin": [0.10, 0.08, 0.10], "s2c": 1.5}},
              "mc": {"sigma_growth": 0.03}}
        a = montecarlo.simulate(co, 0.09, 0.03, 5, 400, seed=7)
        b = montecarlo.simulate(co, 0.09, 0.03, 5, 400, seed=7)
        self.assertEqual(a["v0"], b["v0"])
        self.assertGreater(a["picks"]["bear"], a["picks"]["bull"])

    def test_alpha_suggest_bounds(self):
        s = upside.alpha_suggest({"p_h": {2: 0.9}, "asymmetry": 1000.0, "base_pct": (90.0,), "implied_pct": (10.0,)},
                                 {"upside_full_prob": 0.5, "asym_points_per_doubling": 2.5, "gap_points_per_10pct": 1.0})
        self.assertEqual(s["upside"], 10.0)
        self.assertLessEqual(s["asymmetry"], 10.0)
        self.assertEqual(s["gap"], 10.0)


class TestWaccRegime(unittest.TestCase):
    def test_relever_roundtrip(self):
        bu = wacc.unlever(1.25, 0.8928, 0.25)
        self.assertAlmostEqual(wacc.relever(bu, (1 - 0.8928) / 0.8928, 0.25), 1.25)

    def test_cost_of_capital_net_cash(self):
        reg = {"rf_us": 0.05, "erp": 0.042, "crp": {"US": 0.0023, "KR": 0.0064},
               "industry": {"semiconductor": {"beta": 1.52, "equity_weight": 0.9747}}}
        c = wacc.cost_of_capital(reg, "semiconductor", {"US": 0.5, "KR": 0.5}, 100.0, -20.0, 0.2)
        self.assertEqual(c["debt_weight"], 0.0)          # 순현금이면 부채비중 0
        self.assertAlmostEqual(c["wacc"], c["ke"])
        self.assertAlmostEqual(c["crp"], 0.5 * 0.0023 + 0.5 * 0.0064)

    def test_regime_parse_and_alerts(self):
        self.assertEqual(regime.parse_fred("DATE,DGS10\n2026-10-01,5.10\n2026-10-02,.\n2026-10-03,5.20\n"),
                         [("2026-10-01", 5.10), ("2026-10-03", 5.20)])
        fake = {"DGS10": [(f"2026-10-{i:02d}", 4.6 + 0.05 * i) for i in range(1, 25)]}
        reg = regime.build(fetch=lambda sid, start: fake.get(sid, []), today=date(2026, 10, 28))
        self.assertAlmostEqual(reg["rf_us"], (4.6 + 0.05 * 24) / 100)
        self.assertTrue(any("10년물" in a for a in reg["alerts"]))   # 5영업일 +25bp → 경보


if __name__ == "__main__":
    unittest.main()


class TestFreeData(unittest.TestCase):
    def test_roc_date_and_parsers(self):
        sys.path.insert(0, str(ROOT / "radar" / "markets"))
        sys.path.insert(0, str(ROOT / "radar"))
        import prices_free
        self.assertEqual(prices_free.roc_date("1151027"), "2026-10-27")
        q = prices_free.parse_twse([{"Date": "1151027", "Code": "2330", "ClosingPrice": "2,400.00", "TradeVolume": "100"}])
        self.assertEqual(q["2330.TW"]["close"], 2400.0)
        q2 = prices_free.parse_tpex([{"Date": "1151028", "SecuritiesCompanyCode": "5274", "Close": "3500", "TradingShares": "5"}])
        self.assertEqual(q2["5274.TWO"]["date"], "2026-10-28")

    def test_sec_bulk_annual_revenue(self):
        import sec_bulk
        facts = {"cik": 1, "entityName": "X", "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
            {"start": "2024-01-01", "end": "2024-12-31", "val": 100, "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2025-02-01"},
            {"start": "2024-10-01", "end": "2024-12-31", "val": 30, "fy": 2024, "fp": "FY", "form": "10-K", "filed": "2025-02-01"},
            {"start": "2025-01-01", "end": "2025-12-31", "val": 130, "fy": 2025, "fp": "FY", "form": "10-K", "filed": "2026-02-01"}]}}}}}
        self.assertEqual(sec_bulk.annual_revenue(facts), [(2024, 100), (2025, 130)])   # 분기값은 제외
