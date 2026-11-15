"""국장 주도주 생애 단계(DB금융투자 「주도주의 생로병사」 메커니즘, 2026-11-15) — scripts/discovery/kr_leader.py"""
import csv
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
import kr_leader as kl  # noqa: E402


def weeks(closes, start=date(2024, 1, 1), vols=None):
    return [{"date": (start + timedelta(weeks=i)).isoformat(), "h": c, "c": c, "v": (vols[i] if vols else 100.0)} for i, c in enumerate(closes)]


def bull_index(n_down=50, n_up=30):
    return weeks([100 - 0.2 * i for i in range(n_down)] + [90 + 1.5 * i for i in range(n_up)])


class TestRegime(unittest.TestCase):
    def test_uptrend_start_after_golden_cross(self):
        rg = kl.regime(bull_index(), {"fast_weeks": 10, "slow_weeks": 40})
        self.assertTrue(rg["up"])
        self.assertGreater(rg["age_weeks"], 0)

    def test_not_up_after_fall(self):
        idx = weeks([100 - 0.2 * i for i in range(50)] + [90 + 1.5 * i for i in range(30)] + [135 - 3 * i for i in range(20)])
        rg = kl.regime(idx, {"fast_weeks": 10, "slow_weeks": 40})
        self.assertFalse(rg["up"])
        self.assertIsNotNone(rg["last_seg"])


class TestStages(unittest.TestCase):
    def run_judge(self, stock, index, univ=None, code="000001"):
        with tempfile.TemporaryDirectory() as d:
            st, un = Path(d) / "state", Path(d) / "univ"
            with mock.patch.object(kl, "STATE", st), mock.patch.object(kl, "UNIV", un):
                kl.write_series(st / "index.csv", index)
                kl.write_series(st / f"w_{code}.csv", stock)
                if univ:
                    un.mkdir(parents=True)
                    with (un / "universe_2026-01-01.csv").open("w", encoding="utf-8", newline="") as fh:
                        w = csv.DictWriter(fh, ["code", "name", "perf_1m", "perf_3m", "perf_6m", "perf_y", "perf_ytd", "mcap", "rev_g", "op_g"])
                        w.writeheader()
                        w.writerows(univ)
                return kl.judge(code)

    def univ(self, me, col="perf_1m"):
        rows = [{"code": f"{i:06d}", col: i} for i in range(100, 300)]   # 200종목 0~
        rows.append({"code": "000001", col: me})
        return rows

    def test_early_leader(self):   # 장세 3개월 안 + 상위 5%
        idx = weeks([100 - 0.2 * i for i in range(50)] + [90 + 4 * i for i in range(12)])   # 장세 7주째
        stock = weeks([100.0] * 50 + [100 + 10 * i for i in range(12)])
        j = self.run_judge(stock, idx, self.univ(999, "perf_3m"))
        self.assertTrue(j["stage"].startswith("생"), j)

    def test_drawdown_over_30_is_lost(self):
        idx = bull_index(50, 30)
        stock = weeks([100.0] * 50 + [100 + 5 * i for i in range(20)] + [195 * 0.65] * 10)
        j = self.run_judge(stock, idx, self.univ(999))
        self.assertTrue(j["stage"].startswith("사"), j)

    def test_dead_cross_is_sick(self):
        idx = bull_index(50, 40)
        stock = weeks([100 + 2 * i for i in range(70)] + [240 - 1.2 * i for i in range(20)])   # 천천히 내림(−10%), 10주선 < 40주선
        j = self.run_judge(stock, idx, self.univ(999, "perf_6m"))
        self.assertTrue(j["stage"].startswith(("병", "로")), j)
        if j["price"]["below"]:
            self.assertTrue(j["stage"].startswith("병"))

    def test_outside_rank_ceiling(self):
        idx = bull_index(50, 30)   # 약 7개월 — 6개월 창, 한계 상위 19.8%
        stock = weeks([100.0] * 50 + [100 + 0.5 * i for i in range(30)])
        j = self.run_judge(stock, idx, self.univ(150, "perf_6m"))   # 200개 중 하위권
        self.assertTrue(j["stage"].startswith("해당 없음"), j)

    def test_wording_not_inverse_probability(self):   # 95.3%를 역확률로 쓰지 않는다
        idx = bull_index(50, 30)
        stock = weeks([100.0] * 50 + [100 + 5 * i for i in range(20)] + [195 * 0.65] * 10)
        t = kl.text(self.run_judge(stock, idx, self.univ(999)))
        self.assertNotIn("95.3%", t)
        self.assertIn("매수·매도 지시가 아니다", t)


class TestData(unittest.TestCase):
    def test_bars_from_columns(self):
        r = kl.bars_from({"bars": {"t": [1794182400, 1793577600], "c": [5290.5, 5059.7], "h": [5504.4, 5910.8], "v": [None, None]}})
        self.assertEqual([x["c"] for x in r], [5059.7, 5290.5])
        self.assertEqual(r[0]["v"], 0.0)

    def test_weekly_from_daily(self):
        days = [{"date": f"2026-11-{d:02d}", "h": 10 + d, "c": 10 + d, "v": 1} for d in (9, 10, 11, 12, 13, 16)]
        w = kl.weekly_from_daily(days)
        self.assertEqual(len(w), 2)
        self.assertEqual((w[0]["c"], w[0]["v"], w[0]["h"]), (23, 5, 23))

    def test_ceiling_and_window(self):
        c = kl.cfg()
        self.assertAlmostEqual(kl.ceiling(c, 3), 0.235)
        self.assertEqual(kl.window(5.0), ("perf_6m", 6))

    def test_put_rank(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(kl, "STATE", Path(d)):
                kl.put_rank("000660", "perf_3m", 10, 200)
                self.assertAlmostEqual(kl.rank_file("000660", "perf_3m")["pct"], 0.05)
                self.assertIsNone(kl.rank_file("000660", "perf_6m"))

    def test_registry_bindings(self):
        sys.path.insert(0, str(ROOT / "scripts" / "fit"))
        import registry
        import yaml
        reg = yaml.safe_load((ROOT / "knowledge/models/params/registry.yaml").read_text(encoding="utf-8"))
        ps = [p for p in reg["params"] if p["id"].startswith("prm-krld-")]
        self.assertGreaterEqual(len(ps), 12)
        for p in ps:
            self.assertEqual(registry.resolve(p["binding"]), p["value"], p["id"])


if __name__ == "__main__":
    unittest.main()
