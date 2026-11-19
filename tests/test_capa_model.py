"""캐파 추정 모델(마스터 지시 2026-11-19) — 공시가 없을 때 여러 방법을 합친 추정"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import capa_model as cm  # noqa: E402
import capacity_view as cv  # noqa: E402

EST = {"unit": "$M 매출/년", "output": {"value": 80.0, "label": "TTM 매출", "source": "s"},
       "methods": [{"kind": "자산회전", "base": {"value": 10.0}, "factor": {"lo": 9, "mid": 10, "hi": 11}, "basis": "b", "source": "s"},
                   {"kind": "판매·가동률", "base": {"value": 80.0}, "factor": {"lo": 1 / 0.9, "mid": 1 / 0.8, "hi": 1 / 0.7}, "basis": "b", "source": "s"},
                   {"kind": "경영진", "bound": "하한", "value": 102, "basis": "b", "source": "s"},
                   {"kind": "IB", "value": "미확인", "basis": "b", "source": "s"}]}


class TestCapa(unittest.TestCase):
    def test_weighted_and_floor(self):
        e = cm.estimate({"estimate": EST})
        self.assertAlmostEqual(e["mid"], 102)   # 가중 평균 100 → 경영진 하한 102로 올림
        self.assertEqual(e["lo"], 102)
        self.assertAlmostEqual(e["hi"], 80 / 0.7)
        self.assertAlmostEqual(e["use"], 80 / 102)

    def test_unknown_and_bound_only(self):
        cm.check(EST)
        with self.assertRaises(ValueError):
            cm.check({**EST, "methods": [EST["methods"][2], EST["methods"][3]]})   # 하한·미확인만으로는 추정하지 않는다

    def test_allocation_by_mfg_area(self):
        fac = {"items": [{"name": "A", "use": "제조", "area": {"value": 100}, "capacity_basis": "캐파 미공시 — 제조 사용 비율 50%(10-K)"},
                         {"name": "B", "use": "제조", "area": {"value": 50}}]}
        al = cm.allocate({"mid": 100.0}, fac, cv.is_production)
        self.assertEqual([round(v) for _, v, _ in al], [50, 50])

    def test_disclosed_wins(self):
        self.assertIsNotNone(cm.estimate({"estimate": EST}))
        dp = {"capacity": {"current": {"nameplate": 500, "utilization": 0.8}, "plans": [], "capex": [], "estimate": EST}}
        self.assertEqual(cv.compute(dp)["now"], 500)   # 공시 캐파가 있으면 추정을 쓰지 않는다(charts·section은 now가 None일 때만)


if __name__ == "__main__":
    unittest.main()
