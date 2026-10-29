"""Chiip proviser 품질 점수·단계적 파라미터 설계 시험 (마스터 지시 2026-10-29 — 소수 첫째 자리 평가, 피팅 먼저·추가는 단계적으로)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "proviser"))
sys.path.insert(0, str(ROOT / "scripts" / "fit"))

import harness  # noqa: E402
import quality  # noqa: E402
import stepwise  # noqa: E402

CFG = {"scoring": {"decimals": 1, "axis_step": 0.1, "ops_max": 1.5, "kpi_max_weight": 0.4, "credibility_k": 20}}


class TestQuality(unittest.TestCase):
    def test_one_decimal_and_credibility(self):
        s, rubric, w = quality.final_score([1.6, 1.3, 1.1, 1.2, 1.0], 0.5, 9.3, 40, CFG)
        self.assertAlmostEqual(rubric, 5.7)
        self.assertAlmostEqual(w, round(0.4 * 40 / 60, 3))
        self.assertEqual(s, round((1 - 0.4 * 40 / 60) * 5.7 + 0.4 * 40 / 60 * 9.3, 1))
        self.assertEqual(s, round(s, 1))

    def test_no_kpi_means_rubric_only(self):
        s, rubric, w = quality.final_score([2, 2, 2, 2, 1.94], 0, None, 0, CFG)
        self.assertEqual(w, 0.0)
        self.assertEqual(s, 9.9)   # 1.94 → 0.1 단위로 1.9

    def test_ops_capped(self):
        s, rubric, _ = quality.final_score([2, 2, 2, 2, 2], 3.0, None, 0, CFG)
        self.assertEqual(rubric, 8.5)

    def test_lin_direction(self):
        self.assertEqual(quality.lin(0, 5, 0), 10.0)     # 놓친 사건 0 = 만점(작을수록 좋음)
        self.assertEqual(quality.lin(5, 5, 0), 0.0)
        self.assertEqual(quality.lin(0.15, 0.0, 0.3), 5.0)


class TestStepwise(unittest.TestCase):
    def reg(self, *params):
        return {"adoption": {"min_oos_improvement": 0.05}, "design": {"alpha": 0.05, "obs_per_param": 10, "quality_target": 9.0}, "params": list(params)}

    def test_stage_order(self):
        msys = {"m": ["t"]}
        r = self.reg({"id": "a", "model": "m", "status": "prior", "fit": {"data": None}})
        self.assertEqual(stepwise.stage("m", r, {"t": 7.0}, msys)[0], 0)        # 자료 없으면 데이터 확보부터
        r = self.reg({"id": "a", "model": "m", "status": "prior", "fit": {"data": "x.csv"}})
        self.assertEqual(stepwise.stage("m", r, {"t": 7.0}, msys)[0], 1)        # 자료 있으면 기존 피팅 — 추가 금지
        r = self.reg({"id": "a", "model": "m", "status": "adopted", "fit": {"data": "x.csv", "last_fit": "2026-10-25"}})
        self.assertEqual(stepwise.stage("m", r, {"t": 7.0}, msys)[0], 2)        # 피팅 끝났는데 품질 미달 → 잔차 진단
        self.assertEqual(stepwise.stage("m", r, {"t": 9.4}, msys)[0], 3)        # 목표 충족 → 늘리지 않는다

    def test_nested_test_bonferroni(self):
        base = [1.0 + 0.01 * (i % 5) for i in range(60)]
        ext = [b - 0.12 + 0.02 * ((i * 7) % 5 - 2) for i, b in enumerate(base)]
        ok1, _, st1 = harness.nested_test(base, ext, trials=1)
        self.assertTrue(ok1)
        _, _, st20 = harness.nested_test(base, ext, trials=20)
        self.assertGreater(st20["hurdle"], st1["hurdle"])   # 시도가 쌓일수록 문턱이 오른다(HLZ 2016)
        ok_small, why, _ = harness.nested_test(base, [b * 0.99 for b in base], trials=1)
        self.assertFalse(ok_small)                            # 개선 1% < 5%
        self.assertIn("5%", why)

    def test_obs_per_param_rule(self):
        r = self.reg()
        ok, why, _ = stepwise.can_adopt_extension("m", [1.0] * 25, [0.8] * 25, r, n_params_after=3)
        self.assertFalse(ok)                                   # 25 < 10 × (3 + 1)
        self.assertIn("40", why)

    def test_residual_signal(self):
        f = [float(i) for i in range(30)]
        res = [0.5 * x + ((i * 13) % 7 - 3) * 0.3 for i, x in enumerate(f)]
        self.assertGreater(abs(stepwise.residual_signal(res, f)), 2)


if __name__ == "__main__":
    unittest.main()
