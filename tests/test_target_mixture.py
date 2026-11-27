"""목표주가 = 세 시나리오 수정 가중평균(마스터 지시 2026-11-27 "시장이 반영하는 게 베이스 시나리오 단일에서 다중 시나리오 수정가중평균으로 바뀌었다")"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import target_price as tp  # noqa: E402

S = {"price": 100.0, "bear": 70.0, "base": 100.0, "bull": 140.0, "weighted": 102.5,
     "cases": [{"name": "약세", "multiple": 9.0, "eps": 7.8, "prob": 0.25}, {"name": "기본", "multiple": 12.0, "eps": 8.33, "prob": 0.5},
               {"name": "강세", "multiple": 15.0, "eps": 9.33, "prob": 0.25}]}
CFG = {"weights": {"scenario": 0.35, "dcf": 0.20, "chart": 0.20, "narrative": 0.25}, "narrative_room": {"컨센서스": 0.0, "확산": 0.6},
       "judge_cap": 0.25, "round_above": 20, "prob_lambda": 1.0, "chart": {"near_high": 0.95, "min_gap": 0.01}}


class TestMixture(unittest.TestCase):
    def test_neutral_factors_give_weighted_average_not_base(self):
        pt = tp.build(S, None, 0.1, "컨센서스", None, [], 0.0, 1.0, CFG)
        self.assertAlmostEqual(pt["tilt"], 0.0, places=2)
        self.assertEqual(pt["target"], 102.0)        # 0.25·70 + 0.5·100 + 0.25·140 = 102.5 → 기본 100이 아니다
        self.assertAlmostEqual(sum(pt["probs_mod"].values()), 1.0)

    def test_tilt_moves_probabilities_and_stays_inside(self):
        pt = tp.build(S, None, 0.1, "확산", {"adj": 0.25}, [], 0.0, 1.0, CFG)
        self.assertGreater(pt["probs_mod"]["강세"], pt["probs"]["강세"])
        self.assertGreater(pt["target"], 102.5)
        self.assertLess(pt["target"], S["bull"])
        self.assertIn("수정 가중평균", pt["place"])
        rows = tp.table(pt, dict(S, sym="$"))["rows"]
        self.assertTrue(rows[0][0].startswith("① 시나리오 확률 가중평균"))
        self.assertTrue(rows[-1][0].startswith("**④ 목표주가 = 수정 가중평균"))


if __name__ == "__main__":
    unittest.main()
