"""P·Q 사이클 (마스터 지시 2026-11-03)"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import pq_view as pv  # noqa: E402


def dp(n=20):
    q, asp = [], {}
    for i in range(n):
        d = f"{2021 + i // 4}-{(i % 4) * 3 + 3:02d}-28"
        p = 10 * math.exp(0.15 * math.sin(i * 2 * math.pi / 12))      # 가격은 12분기 주기
        units = 100 * math.exp(0.15 * math.cos(i * 2 * math.pi / 12))  # 물량은 위상이 다르다
        q.append({"period": d, "rev": p * units, "gp": p * units * (0.3 + 0.01 * math.sin(i)), "cogs": None})
        asp[d] = p
    return {"quarters_hist": {"q": q}, "pq": {"price": {"source": "asp", "series": asp}}}


class TestPQ(unittest.TestCase):
    def test_decomposition_adds_up(self):
        for r in pv.decompose(dp()):
            self.assertAlmostEqual(r["g_p"] + r["g_q"], r["g_rev"])

    def test_cycle_and_switch(self):
        c = pv.compute(dp())
        self.assertIn(c["now"], ("P 사이클", "Q 사이클", "동반 하강"))
        self.assertTrue(0 <= c["p_score"] <= 10)
        self.assertIsNotNone(c["proj"])
        self.assertIsNotNone(c["switch"])   # 위상이 다른 주기라 8분기 안에 바뀐다
        s = pv.section(dp())
        self.assertEqual(s["h2"], "P·Q 사이클")

    def test_ar2_period(self):
        y = [math.sin(i * 2 * math.pi / 8) for i in range(30)]
        c, a1, a2 = pv.ar2(y)
        self.assertAlmostEqual(pv.period(a1, a2), 8, delta=0.2)

    def test_none_and_missing(self):
        self.assertIsNone(pv.section({"pq": {"none": "단일 계약 매출"}}))
        with self.assertRaises(SystemExit):
            pv.section({})


if __name__ == "__main__":
    unittest.main()
