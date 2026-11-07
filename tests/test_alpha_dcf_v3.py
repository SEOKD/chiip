"""ADR-016 알파 v2·DCF 보강·SOTP·백테스트 시험 (마스터 승인 2026-11-07)"""
import math
import random
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in ("scripts/valuation/v2", "scripts/alpha", "scripts/backtest", "scripts/fit"):
    sys.path.insert(0, str(ROOT / p))
import calibrate  # noqa: E402
import ic  # noqa: E402
import montecarlo  # noqa: E402
import plus  # noqa: E402
import v2  # noqa: E402


class Plus(unittest.TestCase):
    def test_outside_view_keeps_early_years(self):
        c = {"outside_view": {"enabled": True, "start_year": 3, "k": 0.35}}
        g = [0.4] * 10
        out = plus.outside_view(g, 0.05, c)
        self.assertEqual(out[:3], [0.4] * 3)
        self.assertTrue(all(a > b for a, b in zip(out[3:], out[4:])))
        self.assertLess(abs(out[-1] - 0.05), 0.04)
        self.assertEqual(plus.outside_view(g, None, c), g)

    def test_normalize_ends_at_normal(self):
        out = plus.normalize([0.7] * 10, 0.25, {"normalize": {"blend_years": 3}})
        self.assertAlmostEqual(out[-1], 0.25)
        self.assertEqual(out[:7], [0.7] * 7)

    def test_moat_ronic(self):
        c = {"roic_fade": {"max_spread": 0.08}}
        self.assertAlmostEqual(plus.moat_ronic(0.1, {"moat_score": 0.5}, c), 0.14)
        self.assertAlmostEqual(plus.moat_ronic(0.1, {"ronic_spread": 0.02, "moat_score": 1}, c), 0.12)
        self.assertIsNone(plus.moat_ronic(0.1, {}, c))

    def test_exit_check_flags(self):
        rows = [{"rev": 100, "margin": 0.2, "nopat": 15.0}]
        mult, rng, warn = plus.exit_check({"rows": rows}, {"wacc": 0.10, "g_term": 0.03}, "semiconductor", {"exit_check": {"ranges": {"semiconductor": [8, 25]}}})
        self.assertAlmostEqual(mult, 15 * 1.03 / 0.10 / (100 * 1.03 * 0.2))   # RONIC = WACC → CV = NOPAT·(1+g)/WACC
        self.assertIsNotNone(warn)   # 7.5배 < 8

    def test_t_unit_variance_and_corr(self):
        rng = random.Random(1)
        xs = [montecarlo.corr_pair(rng, 0.4, 5) for _ in range(20000)]
        va = sum(a * a for a, _ in xs) / len(xs)
        cv = sum(a * b for a, b in xs) / len(xs)
        self.assertAlmostEqual(va, 1.0, delta=0.08)
        self.assertAlmostEqual(cv, 0.4, delta=0.05)


class AlphaV2(unittest.TestCase):
    def cfg(self):
        c = v2.cfg()
        c["min_blocks"] = 2
        return c

    def test_ppf_and_rank(self):
        self.assertAlmostEqual(v2.norm_ppf(0.975), 1.959964, places=4)
        z = v2.rank_z({"a": 1, "b": 2, "c": 3})
        self.assertLess(z["a"], 0)
        self.assertAlmostEqual(z["b"], 0)

    def test_better_factors_score_higher(self):
        data = {}
        for i in range(10):
            data[f"c{i}"] = ({"fcf_yield": i / 100, "ebit_ev": i / 50, "book_to_market": i / 10, "roic": i / 20, "log_mcap": 30 - i},
                             {"value": 0, "quality": 0, "discovery": 0}, 0.4)
        rows = v2.compute(date(2026, 11, 7), self.cfg(), data)
        self.assertGreater(rows["c9"]["v2"], rows["c0"]["v2"])
        self.assertAlmostEqual(rows["c9"]["e_alpha"], 0.4 * 0.05 * rows["c9"]["z"], places=3)
        self.assertGreater(rows["c9"]["p_beat_1y"], 0.5)

    def test_stale_block_weighs_less(self):
        c = self.cfg()
        data = {f"c{i}": ({"social_z": i, "fcf_yield": -i}, {"attention": 70, "value": 0}, None) for i in range(10)}
        rows = v2.compute(date(2026, 11, 7), c, data)
        self.assertLess(rows["c9"]["z"], 0)   # 관심 신호가 70일 묵어 가치(반대 방향)가 이긴다


class Backtest(unittest.TestCase):
    def test_ic_detects_signal(self):
        rng = random.Random(3)
        panel = []
        for m in range(72):
            for i in range(40):
                x = rng.gauss(0, 1)
                panel.append({"date": f"m{m:03d}", "id": i, "f": x, "fwd": 0.3 * x + rng.gauss(0, 1)})
        r = ic.test_factor(panel, "f")
        self.assertTrue(r["pass"])
        self.assertAlmostEqual(r["expected_ic"], r["mean_ic"] * 0.5)
        noise = [{**x, "g": rng.gauss(0, 1)} for x in panel]
        self.assertFalse(ic.test_factor(noise, "g")["pass"])

    def test_platt_and_isotonic(self):
        rng = random.Random(5)
        z = [rng.gauss(0, 1) for _ in range(3000)]
        y = [1 if rng.random() < 1 / (1 + math.exp(-(0.2 + 0.8 * x))) else 0 for x in z]
        a, b = calibrate.platt(z, y)
        self.assertAlmostEqual(a, 0.2, delta=0.12)
        self.assertAlmostEqual(b, 0.8, delta=0.12)
        steps = calibrate.isotonic(z, y)
        self.assertTrue(all(p1 <= p2 for (_, p1), (_, p2) in zip(steps, steps[1:])))


if __name__ == "__main__":
    unittest.main()
