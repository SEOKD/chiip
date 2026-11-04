"""신호 가격(밸류·기술 합류) 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import price_levels as pl  # noqa: E402

R, PL = pl.cfg()
REP = {"target": 115.0, "bull": 160.0, "bear": 70.0, "dcf": 110.0, "grade": "Buy", "date": "2026-11-04"}


class T(unittest.TestCase):
    def test_boundary_matches_rating_rule(self):
        import report_layout
        b = pl.boundary(REP, R)
        cfg = {"rating": R}
        p = b["buy"] * 0.999
        up, rr, dcf_up = REP["target"] / p - 1, report_layout.reward_risk(p, REP["bull"], REP["bear"]), REP["dcf"] / p - 1
        self.assertIn(report_layout.rating(up, rr, dcf_up, cfg), ("Buy", "Strong Buy"))
        p = b["buy"] * 1.01
        up, rr, dcf_up = REP["target"] / p - 1, report_layout.reward_risk(p, REP["bull"], REP["bear"]), REP["dcf"] / p - 1
        self.assertNotIn(report_layout.rating(up, rr, dcf_up, cfg), ("Buy", "Strong Buy"))

    def test_confluence_picks_support_near_boundary(self):
        b = pl.boundary(REP, R)["buy"]
        q = {"close": 120.0, "SMA200": b * 0.95, "Pivot.M.Classic.S1": b * 0.7, "Pivot.M.Classic.R1": 140.0}
        lv = pl.levels(REP, q, R, 0.12)
        self.assertEqual(lv["buy"]["basis"], "200일선")

    def test_in_buy_zone_uses_near_support_or_strong_buy(self):
        b = pl.boundary(REP, R)
        q = {"close": b["buy"] * 0.9, "Pivot.M.Classic.S1": b["buy"] * 0.5}
        lv = pl.levels(REP, q, R, 0.12)
        self.assertIn(lv["buy"]["basis"], ("밸류 Strong Buy 경계", "없음"))

    def test_in_sell_zone_without_resistance_has_no_sell_alert(self):
        b = pl.boundary(REP, R)
        lv = pl.levels(REP, {"close": b["sell"] * 1.1}, R, 0.12)
        self.assertIsNone(lv["sell"]["price"])


if __name__ == "__main__":
    unittest.main()
