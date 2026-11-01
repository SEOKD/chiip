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
import report_feed  # noqa: E402
import report_html  # noqa: E402
import report_layout  # noqa: E402
import source_router as sr  # noqa: E402
import target_price as tp  # noqa: E402

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


class TestTargetPrice(unittest.TestCase):
    CFG = {"weights": {"scenario": 0.35, "dcf": 0.2, "chart": 0.2, "narrative": 0.25}, "narrative_room": {"확산": 0.6, "과밀": -0.25, "컨센서스": 0.0}, "judge_cap": 0.25, "round_above": 20, "chart": {"near_high": 0.95, "min_gap": 0.01}}

    def s(self):
        cases = [{"name": "약세", "prob": 0.25, "multiple": 15, "eps": 4, "value": 60}, {"name": "기본", "prob": 0.5, "multiple": 20, "eps": 5, "value": 100}, {"name": "강세", "prob": 0.25, "multiple": 25, "eps": 6, "value": 150}]
        return {"price": 80.0, "bear": 60, "base": 100, "bull": 150, "weighted": 102.5, "cases": cases, "sym": "$"}

    def bars(self, closes):
        return [{"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1000} for i, c in enumerate(closes)]

    def test_target_sits_on_the_scenario_axis(self):
        pt = tp.build(self.s(), 1.5, 0.1, "확산", None, [], 0, 1, self.CFG)
        self.assertGreater(pt["target"], 100)
        self.assertLess(pt["target"], 150)
        self.assertEqual(pt["upside"], pt["target"] / 80 - 1)
        self.assertIn("기본과 강세 사이", pt["place"])

    def test_dcf_alone_does_not_set_the_target(self):
        low = tp.build(self.s(), 0.1, 0.1, "확산", None, [], 0, 1, self.CFG)
        self.assertGreater(low["target"], 60)   # DCF가 낮아도 약세까지 내려가지 않는다

    def test_missing_chart_renormalizes(self):
        pt = tp.build(self.s(), 1.0, 0.1, "컨센서스", None, [], 0, 1, self.CFG)
        self.assertAlmostEqual(sum(x["weight"] for x in pt["factors"]), 1)
        self.assertNotIn("chart", [x["key"] for x in pt["factors"]])

    def test_judgment_is_capped(self):
        a = tp.build(self.s(), 1.0, 0.1, "컨센서스", {"adj": 0.9, "why": "w"}, [], 0, 1, self.CFG)
        self.assertEqual(a["judge"], 0.25)

    def test_chart_targets_resistance_above_price(self):
        closes = [100 + i * 0.5 for i in range(150)] + [175 - i * 0.4 for i in range(120)]
        c = tp.chart_target(self.bars(closes), self.CFG["chart"])
        self.assertGreater(c["price"], closes[-1])
        self.assertIn("저항선", c["why"])

    def test_chart_extends_at_new_high(self):
        closes = [100 + i * 0.5 for i in range(270)]
        c = tp.chart_target(self.bars(closes), self.CFG["chart"])
        self.assertGreater(c["price"], max(closes) * 1.01)

    def test_reach_falls_as_target_rises(self):
        s = self.s()
        self.assertGreater(tp.reach(90, s), tp.reach(100, s))
        self.assertGreater(tp.reach(100, s), tp.reach(140, s))
        self.assertAlmostEqual(tp.reach(100, s), 0.5)

    def test_upside_bars_show_percent(self):
        s = report_html.chart_hbars({"unit": "%", "rows": [{"label": "현재", "bars": [{"name": "a", "value": 13.6}]}]})
        self.assertIn(">13.6%</text>", s)
        self.assertNotIn("%</text>", report_html.chart_hbars({"unit": "배", "rows": [{"label": "현재", "bars": [{"name": "a", "value": 3.5}]}]}))

    def test_dashboard_tile_passes_vendor_scrub(self):
        s = {**self.s(), "target": 110.0, "upside": 0.375, "downside": -0.25, "rr": 3.5}
        mm = {"label_short": "Fwd 1Y P/E", "current": 20.0, "peer_p50": 22.0}
        for ra in ({"buy": 3}, {"buy": 3, "source": "easyconomics"}):
            tiles = report_layout.dashboard({"profile": {"price": 80.0, "debt": 0, "cash": 0}, "consensus": {"ratings": ra}}, s, mm, 6, "Buy", 1.0, "B", "co-none")
            report_html.scrub({"tiles": tiles})

    def test_upside_chart_uses_target(self):
        c = report_layout.upside_chart({"price": 100, "weighted": 120, "target": 110}, [])
        self.assertEqual(c["rows"][0]["bars"][0]["value"], 10.0)


if __name__ == "__main__":
    unittest.main()
