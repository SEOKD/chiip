"""Chiip Consumer 시험 (마스터 지시 2026-10-30 — 비AI 급성장 소비재·게임·콘텐츠IP 국면 판정)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))

import consumer  # noqa: E402
import consumer_attention as ca  # noqa: E402
import pulse  # noqa: E402

CFG = {"phase": {"structural": {"min_growth": 0.20, "min_periods": 4, "max_gm_drop": 0.02}, "upcycle": {"accel_pp": 0.10},
                 "late": {"crowding_pct": 90, "inv_gap_pp": 0.15}, "watch_min": 6.0},
       "weights": {"growth": 0.15, "accel": 0.15, "persistence": 0.10, "margin": 0.10, "sell_through": 0.10, "demand_attention": 0.20, "retail_buzz": 0.05, "runway": 0.15},
       "companies": [{"id": "a", "name": "Steady", "market": "us", "code": "A"}, {"id": "b", "name": "Turn", "market": "us", "code": "B"},
                     {"id": "c", "name": "Fade", "market": "us", "code": "C"}, {"id": "d", "name": "None", "market": "jp", "code": "1"}]}


def quarters(revs, gm=0.5, inv=None):
    ends = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]
    return [{"period": e, "revenue": r, "gross_profit": r * gm, "inventory": (inv[i] if inv else None)} for i, (e, r) in enumerate(zip(ends, revs))]


class TestMetrics(unittest.TestCase):
    def test_quarterly_growth_and_persistence(self):
        m = consumer.metrics(quarters([100, 100, 100, 100, 130, 130, 130, 130, 170, 170]))
        self.assertEqual(m["step"], 4)
        self.assertAlmostEqual(m["growth"], 170 / 130 - 1)
        self.assertEqual(m["persistence"], 6)   # 2025Q1~2026Q2 모두 +20% 이상

    def test_annual_periods_use_step_one(self):
        q = [{"period": f"{y}-03-31", "revenue": r} for y, r in ((2022, 100), (2023, 110), (2024, 150))]
        self.assertEqual(consumer.metrics(q)["step"], 1)

    def test_operating_margin_fallback(self):
        q = [dict(r, gross_profit=None, operating_profit=r["revenue"] * (0.1 if i < 5 else 0.15)) for i, r in enumerate(quarters([100] * 10))]
        m = consumer.metrics(q)
        self.assertEqual(m["margin_basis"], "OPM")
        self.assertGreater(m["gm_change"], 0)

    def test_kabutan_parser(self):
        page = ("<th>3ヵ月決算【実績】</th><td>24.07-09&nbsp;</td><td>67,123</td><td>8,204</td> <td>25.07-09</td><td>68,405</td><td>7,133</td> 前年同期比 "
                "決算期 売上高 前年 同期比 営業益 <td>21.07-09</td><td>41,956</td><td>+15.4</td>")
        q = consumer.kabutan_quarters(page)
        self.assertEqual([r["period"] for r in q], ["2021-09-30", "2024-09-30", "2025-09-30"])
        self.assertEqual(q[1]["operating_profit"], 8204.0)


class TestPhase(unittest.TestCase):
    def test_phases(self):
        fund = {"a": {"q": quarters([100, 100, 100, 100, 130, 130, 130, 130, 170, 170])},
                "b": {"q": quarters([100, 100, 100, 100, 102, 102, 102, 102, 103, 125])},
                "c": {"q": quarters([100, 100, 100, 100, 150, 150, 150, 150, 160, 150], inv=[10] * 5 + [10, 10, 10, 10, 18])}}
        retail = {"c": {"crowding_pct": 95, "accel": 1.0}}
        rows, watch = consumer.evaluate(CFG, fund, {}, retail, {})
        ph = {r["id"]: r["phase"] for r in rows}
        self.assertEqual(ph, {"a": "structural", "b": "upcycle", "c": "late", "d": "nodata"})
        self.assertIn("a", watch)
        self.assertNotIn("c", watch)   # 후반 경고는 watch에서 뺀다

    def test_transition_recorded(self):
        fund = {"a": {"q": quarters([100, 100, 100, 100, 130, 130, 130, 130, 170, 170])}}
        rows, _ = consumer.evaluate(CFG, fund, {}, {}, {"a": {"phase": "neutral"}})
        self.assertEqual(next(r for r in rows if r["id"] == "a")["transition"], "중립 → 구조적 성장")


class TestAttention(unittest.TestCase):
    def test_demand_accel_and_spikes(self):
        o = {"name": "X", "wiki": {"en:Labubu": {"views7": 90000, "base7": 30000, "accel": 3.0}, "en2:Pop Mart": {"views7": 10000, "base7": 10000, "accel": 1.0}},
             "steam": {}, "news": {"Labubu": {"n7": 100, "accel": 9.0, "saturated": True}}}
        self.assertAlmostEqual(ca.demand_accel(o), 2.8)   # 조회 가중 평균, 포화된 뉴스 제외
        sp = ca.spikes({"hk-popmart": o}, 2.0, 20000)
        self.assertEqual([(s["key"], s["accel"]) for s in sp], [("en:Labubu", 3.0)])


class TestPulse(unittest.TestCase):
    def test_consumer_class(self):
        self.assertTrue(pulse.consumer_hits(["jp-takaratomy"]))
        self.assertTrue(pulse.CONSUMER_EVENT_RE.search("タカラトミー[7867]：2027年３月期 第２四半期決算短信"))
        self.assertTrue(pulse.relevant({"title": "タカラトミー 決算", "language": "ja"}, "소비재"))


if __name__ == "__main__":
    unittest.main()
