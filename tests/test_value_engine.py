"""부가가치 엔진(§21.14, ADR-010) 오프라인 테스트 — 등록부·피팅 하네스·논문 관련도·SEC 재무 추출"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "radar" / "markets"))
sys.path.insert(0, str(ROOT / "scripts" / "fit"))

import harness  # noqa: E402
import literature  # noqa: E402
import registry  # noqa: E402
import sec_xbrl  # noqa: E402


class TestRegistry(unittest.TestCase):
    def test_registry_matches_config(self):
        self.assertEqual(registry.check(), [])   # 등록부 값 = config 값

    def test_resolve_and_ids_unique(self):
        self.assertEqual(registry.resolve("config/focus.yaml#threshold"), 5.0)
        ids = [p["id"] for p in registry.load()["params"]]
        self.assertEqual(len(ids), len(set(ids)))
        for p in registry.load()["params"]:
            self.assertIn(p["status"], registry.STATUSES)
            self.assertIn("basis", p["prior"])     # 사전값 근거 필수

    def test_master_fixed_and_approval(self):
        th = next(p for p in registry.load()["params"] if p["id"] == "prm-focus-threshold")
        self.assertTrue(th.get("fixed_by_master"))
        self.assertTrue(registry.needs_approval(0.09, 0.12))    # 33% 변화 → 승인
        self.assertFalse(registry.needs_approval(0.09, 0.095))


class TestHarness(unittest.TestCase):
    def test_walk_forward_no_leak(self):
        for t, idx in harness.walk_forward(10, 4, step=2, horizon=2):
            self.assertTrue(all(i >= t for i in idx))   # 검증은 항상 학습 뒤

    def test_shrink(self):
        self.assertAlmostEqual(harness.shrink(1.0, 0.0, n=10, k=10), 0.5)
        self.assertEqual(harness.shrink(None, 0.3, 5, 5), 0.3)

    def test_evaluate_and_adoption(self):
        # 참값 2.0인 상수 계열: 사전값 0을 표본 밖에서 이겨야 채택
        series = [2.0 + (0.1 if i % 2 else -0.1) for i in range(80)]
        res = harness.evaluate(series, fit_fn=lambda tr: sum(tr) / len(tr),
                               predict_fn=lambda p, te: ([p] * len(te), te), prior=0.0, k=5, min_train=20)
        self.assertLess(res["oos_fit"], res["oos_prior"])
        ok, why = harness.adoption_decision(res["oos_prior"], res["oos_fit"], res["n_oos"],
                                            {"min_oos_n": 30, "min_oos_improvement": 0.05})
        self.assertTrue(ok, why)
        ok, _ = harness.adoption_decision(1.0, 0.99, 100, {"min_oos_n": 30, "min_oos_improvement": 0.05})
        self.assertFalse(ok)                           # 1% 개선은 기각
        ok, _ = harness.adoption_decision(1.0, 0.5, 10, {"min_oos_n": 30})
        self.assertFalse(ok)                           # 표본 부족은 기각

    def test_brier_calibration(self):
        self.assertAlmostEqual(harness.brier([0.8, 0.2], [1, 0]), 0.04)
        rows = harness.calibration([0.9, 0.9, 0.1], [1, 0, 0], bins=2)
        self.assertEqual(rows[-1][4], 2)


class TestLiterature(unittest.TestCase):
    def test_relevance_ranks_domain_papers(self):
        hi, tags = literature.relevance("Measuring Investment in Semiconductor Manufacturing Capacity",
                                        "capital expenditure and the equity risk premium")
        lo, _ = literature.relevance("Household labor supply over the life cycle")
        self.assertGreater(hi, lo)
        self.assertIn("반도체·AI HW", tags)


class TestSecXbrl(unittest.TestCase):
    def test_extract_latest_filed_and_first_concept(self):
        facts = {"facts": {"us-gaap": {
            "Revenues": {"units": {"USD": [
                {"start": "2024-01-29", "end": "2025-01-26", "val": 100, "fy": 2025, "fp": "FY", "form": "10-K", "filed": "2025-02-26"},
                {"start": "2024-01-29", "end": "2025-01-26", "val": 101, "fy": 2026, "fp": "FY", "form": "10-K", "filed": "2026-02-25"},
                {"start": "2024-01-29", "end": "2025-01-26", "val": 999, "fy": 2025, "fp": "FY", "form": "8-K", "filed": "2025-02-20"}]}},
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                {"start": "2024-01-29", "end": "2025-01-26", "val": 5, "fy": 2025, "fp": "FY", "form": "10-K", "filed": "2025-02-26"}]}},
        }}}
        rows = [r for r in sec_xbrl.extract(facts) if r["metric"] == "revenue"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], 101)          # 가장 늦게 제출된 값(재작성 반영)
        self.assertEqual(rows[0]["concept"], "us-gaap:Revenues")  # 개념을 섞지 않음


if __name__ == "__main__":
    unittest.main()
