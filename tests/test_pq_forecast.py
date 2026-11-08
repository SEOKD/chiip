"""P·Q 전망 엔진 재설계 (마스터 지시 2026-11-08 "P 전망, Q 전망이 전문 모델링을 바탕으로 합리적으로 추정되고 있는지 점검 … 체계적으로 바꿔라")"""
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import pq_forecast as F  # noqa: E402
import pq_view as pv  # noqa: E402
import sync_view as sv  # noqa: E402
from tests.test_pq_cycle import dp  # noqa: E402

FC = {"cons_se_floor": 0.05}


class TestAR(unittest.TestCase):
    def test_bic_picks_true_order_and_stays_stationary(self):
        rnd = random.Random(3)
        y = [0.0, 0.0]
        for _ in range(200):
            y.append(0.6 * y[-1] + rnd.gauss(0, 0.02))
        f = F.ar_fit(y)
        self.assertEqual(f["p"], 1)
        self.assertAlmostEqual(f["phi"][0], 0.6, delta=0.12)
        walk = [0.0]
        for _ in range(60):
            walk.append(walk[-1] + rnd.gauss(0, 0.02))   # 단위근 — 그대로 쓰면 갭이 추세로 돌아가지 않는다
        g = F.ar_fit(walk, max_root=0.95)
        self.assertLessEqual(g["radius"], 0.95 + 1e-9)

    def test_forecast_error_grows(self):
        f = {"phi": [0.8], "c": 0.0, "sigma": 0.1}
        m, se = F.ar_path([0.5], f, 4)
        self.assertAlmostEqual(m[0], 0.4)
        self.assertTrue(se[0] < se[1] < se[2] < se[3] < 0.1 / math.sqrt(1 - 0.64) + 1e-9)


class TestConsensus(unittest.TestCase):
    def test_quarters_follow_last_actual_in_order(self):
        d = {"consensus": {"quarters_est": {"2026Q3": 110.8, "2026Q4": 127.3, "2027Q1": 154.7, "2027Q2": 178.8}, "rev": {"FY2027": 416.0, "FY2028": 714.4, "FY2029": 950.0}}}
        out, basis = F.consensus_quarters(d, "2026Q3", 96.2e9, sv.shift_q, 8)
        self.assertEqual(list(out)[:2], ["2026Q4", "2027Q1"])          # 회계 분기 라벨이 달라도 다음 분기부터 순서대로
        self.assertAlmostEqual(out["2026Q4"], 110.8e9, delta=1e6)      # $B → 실적 단위
        self.assertEqual(len(out), 8)
        self.assertIn("연간 컨센서스", basis)

    def test_bad_scale_is_dropped(self):
        d = {"consensus": {"quarters_est": {"2026Q4": 5.0}}}
        self.assertEqual(F.consensus_quarters(d, "2026Q3", 1.0e9 * 50, sv.shift_q)[0], {})

    def test_combination_weights_by_precision(self):
        v, s, w = F.combine(0.0, 0.10, 0.20, 0.05)
        self.assertAlmostEqual(w, 0.8)
        self.assertAlmostEqual(v, 0.16)
        self.assertLess(s, 0.05)


class TestLongCycle(unittest.TestCase):
    def test_consensus_moves_volume_forecast(self):
        d = dp(44)
        rnd = random.Random(7)
        for r in d["quarters_hist"]["q"]:   # 실제 자료처럼 잡음을 넣는다 — 잡음 없는 사인파는 통계 모형이 거의 완벽해 컨센서스 몫이 0에 가깝다(분산 역수 가중 그대로)
            k = math.exp(rnd.gauss(0, 0.06))
            r["rev"], r["gp"] = r["rev"] * k, r["gp"] * k
        base = pv.long_cycle(d, d["pq"])
        last = d["quarters_hist"]["q"][-1]["rev"]
        d2 = {**d, "consensus": {"quarters_est": {f"q{i}": last * 1.3 ** (i + 1) / 1.0 for i in range(4)}}}
        boosted = pv.long_cycle(d2, d2["pq"])
        self.assertGreater(boosted["proj"][3]["g_q"], base["proj"][3]["g_q"] + 0.1)   # 컨센서스가 크게 늘면 물량 전망이 따라 오른다
        self.assertGreater(boosted["proj"][3]["w_cons"], 0)
        self.assertAlmostEqual(boosted["proj"][3]["g_p"], base["proj"][3]["g_p"], delta=0.02)   # 가격 전망은 컨센서스로 바뀌지 않는다
        self.assertTrue(all(x["se_q"] > 0 for x in boosted["proj"]))

    def test_spike_break_cuts_sample(self):
        d = dp(44)
        q = d["quarters_hist"]["q"]
        q[30] = {**q[30], "rev": q[30]["rev"] * 0.45, "gp": q[30]["gp"] * 0.45}   # 재작성 자료처럼 한 분기만 급락했다 되돌린다
        cut, why = pv.breaks(d, pv.levels(d, d["pq"])[0], pv.cfg())
        self.assertIsNotNone(cut)
        lc = pv.long_cycle(d, d["pq"])
        self.assertFalse(lc["enough"])
        self.assertTrue(lc["break"])

    def test_no_premium_chart(self):
        d = dp(44)
        titles = [b["chart"]["title"] for b in pv.section(d)["blocks"] if b["type"] == "chart"]
        self.assertFalse(any("P·Q 프리미엄" in t for t in titles))
        self.assertTrue(any("10년 P·Q 사이클" in t for t in titles))


if __name__ == "__main__":
    unittest.main()
