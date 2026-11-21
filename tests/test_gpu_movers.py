"""GPU 렌털료 계열별 변동 성격 판별·알림 문턱·정체 감지(마스터 지시 2026-11-21 "일일 데이터 변동이 있는 파이프라인을 찾고 이 값이 매일 변할 경우 업데이트할 수 있는 구조")"""
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import gpu_movers as M  # noqa: E402

C = {**M.DEFAULT, "sources": [{"provider": "IDX", "expect": "daily"}, {"provider": "Neb", "expect": "sticky"}]}
TODAY = "2026-11-21"


def rows(provider, vals, config="c", term="t", gpu="H100"):
    d0 = date.fromisoformat(TODAY) - timedelta(days=len(vals) - 1)
    return [{"provider": provider, "gpu": gpu, "config": config, "term": term, "date": (d0 + timedelta(days=i)).isoformat(),
             "usd_per_gpu_hr": "" if v is None else str(v)} for i, v in enumerate(vals)]


class Movers(unittest.TestCase):
    def res(self, rs):
        return M.by_key(M.classify(M.daily_last(rs), TODAY, C))

    def test_classes(self):
        r = self.res(rows("IDX", [3.0, 3.1, 3.05, 3.2, 3.1, 3.15, 3.3, 3.25]) + rows("Neb", [2.95] * 8)
                     + rows("Neb", [2.0] * 7 + [2.5], config="d") + rows("New", [1.0, 1.1]))
        self.assertEqual(r[("IDX", "H100", "c", "t")]["cls"], "daily")
        self.assertEqual(r[("Neb", "H100", "c", "t")]["cls"], "sticky")
        self.assertEqual(r[("Neb", "H100", "d", "t")]["cls"], "occasional")
        self.assertEqual(r[("New", "H100", "c", "t")]["cls"], "new")
        self.assertAlmostEqual(r[("IDX", "H100", "c", "t")]["dd"], -1.52, places=2)

    def test_same_day_last_value_wins(self):
        rs = rows("IDX", [3.0, 3.0]) + [{"provider": "IDX", "gpu": "H100", "config": "c", "term": "t", "date": TODAY, "usd_per_gpu_hr": "3.3"}]
        self.assertEqual(M.daily_last(rs)[("IDX", "H100", "c", "t")][TODAY], 3.3)

    def test_gate_daily_needs_threshold_sticky_any_change(self):
        small = {"cls": "daily", "dd": 1.2, "w1": 3.0}
        big = {"cls": "daily", "dd": -6.0, "w1": -2.0}
        drift = {"cls": "daily", "dd": 0.5, "w1": 11.0}
        self.assertFalse(M.gate(small, 3.0, 3.04, C))
        self.assertTrue(M.gate(big, 3.0, 2.82, C))
        self.assertTrue(M.gate(drift, 3.0, 3.02, C))
        self.assertTrue(M.gate({"cls": "sticky"}, 2.95, 3.10, C))
        self.assertFalse(M.gate({"cls": "sticky"}, 2.95, 2.95, C))
        self.assertTrue(M.gate(None, 2.95, 3.10, C))

    def test_stale_daily_source(self):
        res = M.classify(M.daily_last(rows("IDX", [3.0, 3.1, 3.2] + [3.3] * 8)), TODAY, C)
        self.assertEqual(len(M.stale(res, TODAY, C)), 1)
        self.assertIn("정체 7일", M.stale(res, TODAY, C)[0])
        moving = M.classify(M.daily_last(rows("IDX", [3.0, 3.1, 3.2, 3.3, 3.4, 3.5])), TODAY, C)
        self.assertEqual(M.stale(moving, TODAY, C), [])
        sticky = M.classify(M.daily_last(rows("Neb", [2.95] * 10)), TODAY, C)
        self.assertEqual(M.stale(sticky, TODAY, C), [])   # 정가 원천은 멈춰 있어도 정상

    def test_flopper_median_from_embedded_series(self):
        import gpu_rental as R
        t = ('{key:"a",label:"A",pricingType:"on-demand",points:[{day:"2026-11-20",usd:2.0},{day:"2026-11-21",usd:2.0}]},'
             '{key:"b",label:"B",pricingType:"on-demand",points:[{day:"2026-11-20",usd:3.0},{day:"2026-11-21",usd:3.5}]},'
             '{key:"c",label:"C",pricingType:"on-demand",points:[{day:"2026-11-20",usd:5.0},{day:"2026-11-21",usd:4.0}]},'
             '{key:"a2",label:"A",pricingType:"on-demand",points:[{day:"2026-11-21",usd:9.9}]},'   # 같은 제공사 두 번째 — 뺀다
             '{key:"s",label:"S",pricingType:"spot",points:[{day:"2026-11-21",usd:0.5}]}')        # 스팟은 뺀다
        got = R.flopper({"https://flopper.io/pricing/nvidia-h100": t}, history=True)
        self.assertEqual([(r["date_obs"], r["usd_per_gpu_hr"]) for r in got], [("2026-11-20", 3.0), ("2026-11-21", 3.5)])
        self.assertEqual(R.flopper({"https://flopper.io/pricing/nvidia-h100": t})[0]["date_obs"], "2026-11-21")

    def test_gcp_spot_machine_price_per_gpu(self):
        import gpu_rental as R
        t = ("<td>a3-highgpu-8g</td><td>Nvidia H100 GPUs: 8</td><td>vCPUs: 208</td><td>$52.700460712 / 1 hour</td>"
             "<td>a4-highgpu-8g</td><td>Nvidia B200 GPUs: 8</td><td>$43.5968 / 1 hour</td>")
        got = {r["gpu"]: r["usd_per_gpu_hr"] for r in R.gcp_spot(t)}
        self.assertEqual(got, {"H100": 6.588, "B200": 5.45})

    def test_daily_caption_warns_stale(self):
        import gpu_daily as D
        cap = D.caption({"until": TODAY, "gpus": [], "index": {}, "stale": ["Silicon Data 지수 정체 7일(마지막 변화 11/14)"]})
        self.assertIn("주의: Silicon Data 지수 정체 7일", cap)


if __name__ == "__main__":
    unittest.main()
