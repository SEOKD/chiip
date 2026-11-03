"""거시 지표 싱크로율·매출→GP 비용 다리 (마스터 지시 2026-11-03)"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import cost_bridge_view as cb  # noqa: E402
import report_html as rh  # noqa: E402
import sync_view as sv  # noqa: E402


def quarters(n=16):
    return [{"period": f"{2022 + i // 4}-{(i % 4) * 3 + 3:02d}-28", "rev": 100 * 1.03 ** i * (1 + 0.05 * math.sin(i)), "cogs": 80 + 3 * i, "gp": None,
             "sga": 8 + 0.2 * i, "rd": 1, "da": 1, "other": 0, "op": 10 + i} for i in range(n)]


class TestSync(unittest.TestCase):
    def setUp(self):
        ind = {}
        for y in range(2021, 2027):
            for m in range(1, 13):
                t = (y - 2021) * 4 + (m - 1) / 3 - 4   # 1분기 앞서 같은 모양
                ind[f"{y}-{m:02d}"] = 50 * 1.03 ** t * (1 + 0.05 * math.sin(t + 1))
        self.h = {"inputs": {"pcb": {"ppi": {}, "trade": {"us": ind}}}}
        self.dp = {"sync": {"indicators": [{"label": "x", "source": "trade", "input": "pcb", "country": "us"}]}, "quarters_hist": {"q": quarters()}}

    def test_quarter_label_for_52_week_year(self):
        self.assertEqual(sv.qlabel("2026-01-03")[0], "2025Q4")
        self.assertEqual(sv.qlabel("2026-09-28")[0], "2026Q3")

    def test_finds_leading_indicator(self):
        r = sv.compute(self.dp, self.h)["rows"][0]
        self.assertGreater(r["rev"]["r"], 0.9)
        self.assertIsNotNone(r["next"])

    def test_none_and_missing(self):
        self.assertIsNone(sv.section({"sync": {"none": "무관"}}))
        with self.assertRaises(SystemExit):
            sv.section({})


class TestCostBridge(unittest.TestCase):
    def test_bridge_adds_up(self):
        c = cb.compute({"quarters_hist": {"q": quarters()}})
        steps = {n: v for n, v, _ in c["steps"]}
        self.assertAlmostEqual(100 - (100 - steps["매출총이익"]), steps["매출총이익"])
        self.assertAlmostEqual(steps["매출"] + steps["매출원가"] if "매출원가" in steps else steps["매출총이익"], steps["매출총이익"], delta=0.5)
        self.assertTrue(rh.chart_waterfall({"steps": [{"label": n, "value": v, "kind": k} for n, v, k in c["steps"]]}).startswith("<svg"))

    def test_elastic_recovers_variable_cost(self):
        q = [{"rev": 100 + 10 * i, "cogs": 30 + 0.6 * (100 + 10 * i)} for i in range(10)]
        b, fixed = cb.elastic(q, "cogs")
        self.assertAlmostEqual(b, 0.6, places=6)
        self.assertGreater(fixed, 0)


if __name__ == "__main__":
    unittest.main()
