"""SPAC 비대칭 점수 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import spac_score as ss  # noqa: E402

C = ss.cfg()
BASE = {"price": 10.0, "trust_per_share": 10.2, "cash": {"trust_left": 0.2, "pipe": 0.05, "fees": 0.02}, "shares": {"공개 주주(환매 후)": 20, "스폰서": 5, "피인수 기존 주주": 50},
        "fairness": {"base": 1.0}, "lockups": []}


class T(unittest.TestCase):
    def test_floor_before_redemption_only(self):
        pre = ss.score(BASE, "S3", True, C)
        self.assertIn("floor", pre["factors"])
        post = ss.score({**BASE, "redemption": {"pct": 0.6}}, "S4", True, C)
        self.assertNotIn("floor", post["factors"])

    def test_net_cash_per_share(self):
        r = ss.score(BASE, "S3", True, C)
        self.assertAlmostEqual(r["numbers"]["net_cash_ps"], 0.23 * 1000 / 75, places=2)

    def test_kill_caps_score(self):
        r = ss.score({**BASE, "redemption": {"pct": 0.97}, "cash": {"trust_left": 0.01}}, "S4", True, C)
        self.assertIn("환매 95% 이상·PIPE 없음", r["kills"])
        self.assertLessEqual(r["score"], C["kill_cap"])
        self.assertFalse(r["candidate"])

    def test_overhang_penalizes_big_unlock(self):
        lock = {**BASE, "lockups": [{"date": "2000-01-01", "shares": 60}]}
        self.assertLess(ss.score(lock, "S5", True, C)["factors"]["overhang"], ss.score(BASE, "S5", True, C)["factors"]["overhang"])

    def test_base_rate_line(self):
        line = ss.score(BASE, "S5", True, C)["base_rate"]
        self.assertIn("10배", line)
        self.assertIn("생존 편향", line)

    def test_value_log_scale(self):
        cheap = {**BASE, "projections": [{"rev": 1.0}], "peer_ev_rev": 4.0}
        r = ss.score(cheap, "S5", True, C)
        self.assertGreater(r["factors"]["value"], 5)


if __name__ == "__main__":
    unittest.main()
