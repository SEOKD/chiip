"""다음 분기 추정 — 표본 밖 검증·예측 결합·외삽 제한·세그먼트→전사(마스터 지시 2026-11-08 '전문 기법 점검')"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import sync_view as sv  # noqa: E402

Q = [f"{y}Q{q}" for y in range(2020, 2027) for q in range(1, 5)][:27]   # 2020Q1~2026Q3


class TestForecast(unittest.TestCase):
    def test_useless_indicator_loses_to_naive(self):
        import math
        rev, v = {}, 100.0
        for i, q in enumerate(Q):                                                 # 증가율이 천천히 변한다 — 직전 증가율 지속(기준선)이 잘 맞는다
            v *= 1 + 0.02 + 0.01 * math.sin(i / 4)
            rev[q] = v
        ind = {q: 100 + (13 * i % 7) * 10 for i, q in enumerate(Q)}                # 잡음 지표
        fr = sv.fit(rev, ind, 4)
        ev = sv.oos(rev, ind, fr, 4, Q[-1])
        self.assertIsNotNone(ev)
        self.assertLess(ev["w"], 0.5)                                              # 결합 가중이 기준선 쪽

    def test_clip_outside_range(self):
        ind = {q: 100 + i for i, q in enumerate(Q)}
        x, cut = sv.clip_x(ind, 4, 5.0)
        self.assertTrue(cut)
        self.assertLess(x, 1.0)

    def test_segment_to_total_adds_other(self):
        rev = {"2025Q4": 1000.0, "2026Q2": 1100.0, "2026Q3": 1200.0, "2025Q3": 900.0, "2025Q2": 850.0}
        seg = {k: v * 0.4 for k, v in rev.items()}
        c = {"rev": rev, "next": "2026Q4"}
        top = {"target": "Vehicle Payments", "k": 4, "comp": seg}
        tot = sv.to_total(c, top, {"rev": 430.0, "lo": 400.0, "hi": 460.0})
        other_g = (1200 * 0.6) / (900 * 0.6) - 1                                   # 나머지 사업의 직전 전년 대비
        self.assertAlmostEqual(tot["rev"], 430 + 600 * (1 + other_g), places=6)
        self.assertGreater(tot["rev"], 1000)                                        # 세그먼트 값을 전사로 쓰지 않는다(CPAY 반토막 버그)


if __name__ == "__main__":
    unittest.main()
