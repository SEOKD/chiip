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

    def test_hp_keeps_linear_trend(self):
        y = [0.1 * i for i in range(30)]
        for a, b in zip(pv.hp(y, 1600), y):
            self.assertAlmostEqual(a, b, places=6)

    def test_long_cycle_position_premium(self):
        d = dp(44)
        lc = pv.long_cycle(d, d["pq"])
        self.assertTrue(lc["enough"])
        self.assertIn(lc["type"], ("P형", "Q형"))
        self.assertIn(lc["clock_p"], ("회복", "확장", "둔화", "수축"))
        for x in lc["pts"]:
            self.assertTrue(-1 <= x["prem_p"] <= 1 and -1 <= x["prem_q"] <= 1)
        self.assertEqual(len(lc["proj"]), 8)
        s = pv.section(d)
        self.assertTrue(any(b.get("chart", {}).get("now") for b in s["blocks"] if b["type"] == "chart"))

    def test_premium_signs(self):
        c = {"premium_cap": 1.0, "p_dropthrough": 1.0}
        p, q = pv.premiums(0.1, -0.1, 0.4, 0.5, c)
        self.assertGreater(p, 0)
        self.assertLess(q, 0)
        self.assertEqual(pv.premiums(2, 0, 0.1, 0.1, c)[0], 1.0)   # ±100%에서 자른다

    def test_fred_proxy_when_none(self):
        d = dp(44)
        asp = d["pq"]["price"]["series"]
        cache = {"PCU334413334413": {f"{k[:5]}{int(k[5:7]) - m:02d}": v for k, v in asp.items() for m in range(3)}}
        d2 = {"quarters_hist": d["quarters_hist"], "industry": "semiconductor", "pq": {"none": "ASP 비공시"}}
        s = pv.section(d2, fred_cache=cache)
        self.assertIn("대용", s["blocks"][-1]["text"])
        self.assertIn("ASP 비공시", s["blocks"][-1]["text"])

    def test_none_and_missing(self):
        self.assertIsNone(pv.section({"pq": {"none": "단일 계약 매출"}}))
        with self.assertRaises(SystemExit):
            pv.section({})


if __name__ == "__main__":
    unittest.main()
