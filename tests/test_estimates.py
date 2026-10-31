"""발표 전 추정 저장과 2순위 번갈아 쓰기·보완 (마스터 지시 2026-11-01)"""
import sys
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fiscal"))
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import earnings_view  # noqa: E402
import estimates as es  # noqa: E402
import source_router as sr  # noqa: E402

CFG = {"limits": {"easyconomics": {"daily_cap": 2, "cooldown_h": 24}}, "items": {"quarter_est": {"tier2": ["zacks", "easyconomics"]}, "eps_revision": {"tier2": ["zacks"]}}}
NOW = datetime(2026, 11, 1, 9, 0)


def snap(saved, mean, metric="revenue", basis="gaap", source="agentic_consensus"):
    return {"saved": saved, "key": "K", "report_date": "2026-09-30", "period": "2026Q3", "metric": metric, "mean": str(mean), "source": source, "basis": basis, "as_of": saved}


def row(metric="매출", est=100.0, src="zacks", actual=110.0, basis="gaap"):
    return {"period": "2026Q3", "report_date": "2026-09-30", "metric": metric, "actual": actual, "est": est, "est_src": src, "basis": basis, "earnings_date": "2026-10-28"}


EC = {"2026Q3": {"sales_actual": 110.5, "sales_estimate": 102.0, "eps_actual": 1.04, "eps_estimate": 0.86}}


class TestRouter(unittest.TestCase):
    def test_alternates(self):
        self.assertEqual(sr.order("quarter_est", {}, CFG, NOW), ["zacks", "easyconomics"])
        self.assertEqual(sr.order("quarter_est", {"turns": {"quarter_est": 1}}, CFG, NOW), ["easyconomics", "zacks"])
        self.assertEqual(sr.order("quarter_est", {"turns": {"quarter_est": 2}}, CFG, NOW), ["zacks", "easyconomics"])

    def test_capped_source_goes_last(self):
        st = {"turns": {"quarter_est": 1}, "sources": {"easyconomics": {"day": "2026-11-01", "calls": 2}}}
        self.assertEqual(sr.order("quarter_est", st, CFG, NOW), ["zacks", "easyconomics"])
        st["sources"]["easyconomics"]["day"] = "2026-10-31"
        self.assertEqual(sr.order("quarter_est", st, CFG, NOW), ["easyconomics", "zacks"])

    def test_cooldown(self):
        st = {"turns": {"quarter_est": 1}, "sources": {"easyconomics": {"until": "2026-11-02T00:00:00"}}}
        self.assertEqual(sr.order("quarter_est", st, CFG, NOW)[0], "zacks")

    def test_single_source_item(self):
        self.assertEqual(sr.order("eps_revision", {"turns": {"eps_revision": 3}}, CFG, NOW), ["zacks"])


class TestStore(unittest.TestCase):
    def test_only_changed_values_are_added(self):
        rows = [{"key": "K", "reportDate": "2026-09-30", "period": "2026Q3", "metrics": {"revenue": {"mean": 100, "source": "model", "basis": "gaap", "asOf": "2026-10-01"}}}]
        first = es.new_lines(rows, [], "2026-10-02")
        self.assertEqual(len(first), 1)
        self.assertEqual(es.new_lines(rows, [{k: str(v) for k, v in first[0].items()}], "2026-10-03"), [])
        rows[0]["metrics"]["revenue"]["mean"] = 101
        self.assertEqual(len(es.new_lines(rows, [{k: str(v) for k, v in first[0].items()}], "2026-10-03")), 1)

    def test_values_saved_after_release_are_ignored(self):
        got = es.frozen([snap("2026-10-20", 1e8), snap("2026-10-28", 2e8), snap("2026-10-29", 3e8)], "K", "2026-09-30", "2026-10-28")
        self.assertEqual(got["revenue"]["mean"], "100000000.0")


class TestFill(unittest.TestCase):
    def test_stored_fiscal_beats_second_tier(self):
        r = row()
        d = es.fill_rows([r], "K", [snap("2026-10-20", 105e6)], EC, "easyconomics")
        self.assertEqual((r["est"], r["est_src"], d["stored"]), (105.0, "fiscal:agentic_consensus", 1))
        self.assertEqual(r["pair"], {"zacks": 100.0})

    def test_fresh_fiscal_row_is_untouched(self):
        r = row(est=99.0, src="fiscal:guidance")
        es.fill_rows([r], "K", [snap("2026-10-20", 105e6)], EC)
        self.assertEqual(r["est"], 99.0)

    def test_stored_eps_needs_same_basis(self):
        r = row("EPS", 0.8, actual=1.04, basis="adjusted")
        es.fill_rows([r], "K", [snap("2026-10-20", 0.5, "eps_adjusted", "gaap")], {}, "zacks")
        self.assertEqual(r["est_src"], "zacks")

    def test_turn_decides_between_second_tier(self):
        a, b = row(), row()
        es.fill_rows([a], "K", [], EC, "zacks")
        es.fill_rows([b], "K", [], EC, "easyconomics")
        self.assertEqual((a["est_src"], a["est"]), ("zacks", 100.0))
        self.assertEqual((b["est_src"], b["est"]), ("easyconomics", 102.0))

    def test_each_fills_the_others_gap(self):
        a = row(est=None, src=None)
        d = es.fill_rows([a], "K", [], EC, "zacks")
        self.assertEqual(a["est_src"], "easyconomics")
        self.assertEqual(d["empty"], [])
        b = row("EBIT", 20.0, actual=30.0, basis="adjusted")
        es.fill_rows([b], "K", [], EC, "easyconomics")   # EBIT 추정은 Easyconomics에 없다
        self.assertEqual(b["est_src"], "zacks")

    def test_mismatched_actual_is_rejected(self):
        r = row(est=None, src=None, actual=300.0)   # 다른 기준·다른 기간
        d = es.fill_rows([r], "K", [], EC, "easyconomics")
        self.assertIsNone(r["est"])
        self.assertEqual(d["empty"], ["2026Q3 매출"])

    def test_wide_gap_is_reported(self):
        d = es.fill_rows([row(est=50.0)], "K", [], EC, "zacks")
        self.assertEqual(len(d["gaps"]), 1)

    def test_margin_keeps_same_provider_pair(self):
        rows = [row(est=100.0), row("EBIT", 20.0, actual=33.0, basis="adjusted")]
        es.fill_rows(rows, "K", [], EC, "easyconomics")
        _, out = earnings_view.margin_surprises(rows)
        self.assertAlmostEqual(out[0]["est"], 20.0)

    def test_attribution_follows_use(self):
        out = {"key": "K", "rows": [row()]}
        es.apply_surprise(out, [snap("2026-10-20", 105e6)])
        self.assertFalse(out["zacks_used"])
        self.assertIsNone(out["attribution"])

    def test_pick_uses_stored_value(self):
        out = {"key": "K", "reported": "2026-09-30", "period": "2026Q3", "earningsDate": "2026-10-28", "reported_actual": {"revenue": 110e6, "revenue_basis": "gaap"},
               "pick": {"reported": {"revenue": {"est": 100e6, "src": "zacks"}}, "guidance": None}, "zacks_used": True}
        es.apply_pick(out, [snap("2026-10-20", 105e6)])
        self.assertEqual(out["pick"]["reported"]["revenue"]["est"], 105e6)
        self.assertFalse(out["zacks_used"])


class TestStreet(unittest.TestCase):
    P = {"data": {"analyst_total": 11, "analyst_buy": 7, "analyst_hold": 4, "analyst_sell": 0, "target_price": 152.2, "target_price_high": 200, "target_price_low": 110}}
    Z = {"strong_buy": 6, "buy": 1, "hold": 5, "sell": 0, "strong_sell": 0, "as_of": "2026-10-20"}

    def test_zacks_turn_borrows_target(self):
        s = es.street(self.Z, self.P)
        self.assertEqual(s["strong_buy"], 6)
        self.assertEqual(s["target_mean"], 152.2)
        self.assertNotIn("source", s)

    def test_easyconomics_turn(self):
        s = es.street(self.Z, self.P, "easyconomics", "2026-11-01")
        self.assertEqual((s["buy"], s["strong_buy"], s["source"]), (7, 0, "easyconomics"))

    def test_fills_when_zacks_is_empty(self):
        self.assertEqual(es.street({}, self.P, "zacks", "2026-11-01")["buy"], 7)


if __name__ == "__main__":
    unittest.main()
