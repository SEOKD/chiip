"""시나리오 확률 근거 계산 (마스터 지시 2026-11-14 "약세와 강세 확률이 각 25%씩으로 계산이 많이 되는데 이 확률 체계를 다시 점검하라", ADR-035)"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
import build_drivers  # noqa: E402
import scenario_prob as sp  # noqa: E402


class TestCompute(unittest.TestCase):
    def test_sums_and_order(self):
        r = sp.compute(0.10, 0.05, 0.15, 1.0, 1.06, 1.14, 12, 3e9)
        self.assertAlmostEqual(r["bear"] + r["base"] + r["bull"], 1.0)
        self.assertTrue(all(r[k] >= 0.05 for k in ("bear", "base", "bull")))
        self.assertIsNone(sp.compute(0.10, 0.05, 0.02, 1.0))   # 강세 < 기본이면 계산하지 않는다

    def test_wider_scenarios_shift_mass_to_base(self):
        narrow = sp.compute(0.10, 0.08, 0.12, 1.0, 1.06, 1.14, 12)
        wide = sp.compute(0.10, 0.0, 0.20, 1.0, 1.06, 1.14, 12)
        self.assertGreater(wide["base"], narrow["base"])   # 시나리오가 멀수록 기본 쪽 확률이 크다

    def test_skew_follows_consensus_position(self):
        # 약세가 기본에 가깝고 강세가 멀면 약세 확률이 더 크다
        r = sp.compute(0.10, 0.08, 0.20, 1.0, 1.06, 1.14, 12)
        self.assertGreater(r["bear"], r["bull"])

    def test_more_analysts_tighter(self):
        few = sp.inside_sigma(1.0, 1.06, 1.14, 3, sp.cfg())[0]
        many = sp.inside_sigma(1.0, 1.06, 1.14, 20, sp.cfg())[0]
        self.assertGreater(few, many)   # 같은 범위라도 애널리스트가 적으면 σ가 크다(d2)

    def test_no_range_grows_with_growth(self):
        c = sp.cfg()
        self.assertGreater(sp.inside_sigma(1.0, None, None, None, c, 0.5)[0], sp.inside_sigma(1.0, None, None, None, c, 0.05)[0])

    def test_outside_view_pulls_toward_base_rate(self):
        hi_growth = sp.compute(0.60, 0.40, 0.80, 1.0, 1.4, 1.8, 6, out_sample=[0.0, 0.05, 0.1] * 50)
        no_out = dict(sp.cfg(), outside_weight=0.0)
        base = sp.compute(0.60, 0.40, 0.80, 1.0, 1.4, 1.8, 6, c=no_out, out_sample=[0.0, 0.05, 0.1] * 50)
        self.assertGreater(hi_growth["bear"], base["bear"])   # 실제 기업 성장 분포가 낮으면 약세 쪽으로

    def test_judge_cap(self):
        eng = {"bear": 0.30, "base": 0.40, "bull": 0.30}
        p, why = sp.judged(eng, {"bear": 0.05, "base": 0.5, "bull": 0.45}, "가이던스 상향")
        self.assertEqual((p["bear"], p["bull"]), (0.2, 0.4))   # ±0.10 안으로
        p2, why2 = sp.judged(eng, {"bear": 0.05, "base": 0.5, "bull": 0.45}, None)
        self.assertEqual(p2, eng)   # 이유 없으면 엔진 그대로
        self.assertIsNone(why2)


class TestApply(unittest.TestCase):
    def test_apply_sets_probs_and_flags_bad_order(self):
        co = {"rev0": 1.0, "unit_usd": 1e9, "scenarios": {"bear": {"growth": {"start": 0.05}}, "base": {"growth": {"start": 0.10}}, "bull": {"growth": {"start": 0.15}}}}
        dp = {"consensus": {"rev": {"FY26": 1.0, "FY27": 1.1}, "rev_low": {"FY26": 1.0, "FY27": 1.06}, "rev_high": {"FY26": 1.0, "FY27": 1.14}, "n_analysts": 10}}
        r = sp.apply(co, dp)
        self.assertEqual(r["status"], "계산")
        self.assertAlmostEqual(sum(co["scenarios"][k]["prob"] for k in ("bear", "base", "bull")), 1.0)
        co["scenarios"]["bull"]["growth"]["start"] = 0.01
        co.pop("scenario_prob")
        self.assertEqual(sp.apply(co, dp)["status"], "계산 불가")


class TestBuildDriversRange(unittest.TestCase):
    def test_bull_uses_next_year_high(self):
        p = {"id": "x", "name": "X", "industry": "software", "unit": "B$", "tax": 0.21, "region_mix": {"US": 1.0},
             "profile": {"price": 10, "shares_basic": 1.0, "cash": 0, "debt": 0},
             "financials": {"rev_ttm": 1.0, "ebit_ttm": 0.1, "invested_capital": 1.0},
             "consensus": {"rev": {"FY2026": 1.0, "FY2027": 1.5}, "rev_low": {"FY2026": 0.98, "FY2027": 1.3}, "rev_high": {"FY2026": 1.02, "FY2027": 1.7},
                           "n_analysts": 10, "ebit_margin": {"FY2026": 0.1, "FY2027": 0.12}, "margin_basis": "gaap", "rev_basis": "gaap"},
             "call": {"tone": "flat"}}
        d = build_drivers.build(p)
        g = {k: d["scenarios"][k]["growth"]["start"] for k in ("bear", "base", "bull")}
        self.assertLess(g["bear"], g["base"])
        self.assertLess(g["base"], g["bull"])   # 그전엔 올해 최고(1.02)를 써서 강세 2% < 기본 50%였다
        self.assertAlmostEqual(g["bull"], 0.7, places=3)
        self.assertIn("근거 계산", d["provenance"]["probs"])


if __name__ == "__main__":
    unittest.main()
