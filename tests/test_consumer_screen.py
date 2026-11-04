"""소비재 지도 밖 발굴·복리 성장 국면 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "discovery"))
import consumer_screen as cs  # noqa: E402
import consumer  # noqa: E402

C = cs.cfg()


def row(sym, g, gm, mc=5e9, ind="Electronics/Appliances"):
    return {"symbol": sym, "description": sym, "industry": ind, "market_cap_basic": mc, "total_revenue_yoy_growth_ttm": g, "gross_margin_ttm": gm}


class T(unittest.TestCase):
    def test_gates(self):
        out = cs.screen([row("NYSE:AAA", 20, 45), row("OTC:BBB", 30, 60), row("NYSE:CCC", 300, 40), row("NYSE:DDD", 25, 15),
                         row("NASDAQ:EEE", 18, 50, ind="Motor Vehicles"), row("NYSE:FFF", 15, 40, mc=5e8)], C, known=set())
        self.assertEqual([x["code"] for x in out], ["AAA"])
        self.assertEqual(out[0]["segment"], "household_durables")
        self.assertEqual(out[0]["fiscal"], "NYSE_AAA")

    def test_known_skipped(self):
        self.assertEqual(cs.screen([row("NYSE:SN", 20, 50)], C, known={"SN"}), [])

    def test_compounder_phase(self):
        q, rev = [], 100.0
        for i in range(12):
            rev *= 1.035   # 분기 +3.5% ≈ 연 +15%
            q.append({"period": f"20{24 + i // 4}-{3 * (i % 4) + 3:02d}-28", "revenue": rev, "gross_profit": rev * (0.45 + 0.003 * i), "inventory": rev * 0.5})
        rows, watch = consumer.evaluate(cfg={**consumer._y("config/consumer.yaml"), "companies": [{"id": "x", "name": "X", "market": "us", "code": "X"}]},
                                        fund={"x": {"q": q}}, demand={}, retail={}, prev={})
        self.assertEqual(rows[0]["phase"], "compounder")
        self.assertIn("x", watch)


if __name__ == "__main__":
    unittest.main()
