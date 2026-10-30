"""텐배거 리포트 개정 양식 시험 (마스터 지시 2026-10-30 — 배수 사다리·내러티브 선두·참고 문헌 제거·그림 3·5·8)"""
import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))

import ladder  # noqa: E402
import narrative_view  # noqa: E402
import report_html  # noqa: E402
import report_md  # noqa: E402
import report_notion  # noqa: E402
import revision_view as rv  # noqa: E402
import v2_to_report  # noqa: E402


def chart(title, pin=None):
    c = {"kind": "line", "title": title, "series": [{"name": "s", "points": [["a", 1], ["b", 2]]}]}
    if pin:
        c["pin"] = pin
    return {"type": "chart", "chart": c}


BASE = {"title": "t", "date": "2026-10-30", "ticker": "T", "company": "C", "biz": "b", "sources": ["Fiscal.ai"]}


class TestLadder(unittest.TestCase):
    def test_tiers_follow_market_cap(self):
        self.assertEqual(ladder.steps_for(29.9e9), [2, 3, 5, 10])
        self.assertEqual(ladder.steps_for(30e9), [2, 3, 5])
        self.assertEqual(ladder.steps_for(99.9e9), [2, 3, 5])
        self.assertEqual(ladder.steps_for(100e9), [2])
        self.assertEqual(ladder.steps_for(3e12), [2])

    def _inputs(self, mcap=2.0):
        co = {"rev0": 2.0, "unit_usd": 1e9, "market": {"net_debt": 0.3}}
        r = {"mcap": mcap, "unit": "B$", "upside": {"p_h": {2: 0.4, 3: 0.2, 5: 0.05, 10: 0.0}, "required": {2: (0.2, (60.0, 100, "")), 3: (0.3, (90.0, 100, "")), 5: (0.5, (98.0, 100, "")), 10: (0.7, (100.0, 100, ""))}}}
        steps = {str(k): {"path": "p", "outlook": "o", "verdict": "v"} for k in (2, 3, 5, 10)}
        dp = {"ladder": {"exit": {"pe": 20, "net_margin": 0.1}, "market": {"name": "M", "size": 100}, "steps": steps}}
        return dp, co, r

    def test_required_revenue(self):
        dp, co, r = self._inputs()
        c = ladder.compute(dp, co, r)
        x = c["rows"][0]
        self.assertAlmostEqual(x["target"], 4.0)
        self.assertAlmostEqual(x["profit"], 0.2)
        self.assertAlmostEqual(x["rev"], 2.0)
        self.assertAlmostEqual(c["rows"][3]["rev"], 10.0)
        self.assertAlmostEqual(c["rows"][1]["share"], 0.03)

    def test_section_needs_every_step(self):
        dp, co, r = self._inputs()
        del dp["ladder"]["steps"]["5"]
        with self.assertRaises(ValueError):
            ladder.report_section(dp, co, r)

    def test_large_cap_shows_only_two_times(self):
        dp, co, r = self._inputs(mcap=150.0)
        sec = ladder.report_section(dp, co, r)
        self.assertIn("2배", sec["h2"])
        self.assertNotIn("3", sec["h2"])
        self.assertEqual(ladder.summary_item(dp, co, r)["q"], "2배가 되려면?")


class TestLeadAndMerge(unittest.TestCase):
    def lead(self):
        return {"summary": "s", "value_story": "v", "products": [{"kind": "제품", "name": "n", "what": "w"}],
                "lenses": [{"lens": k, "change": "c"} for k in narrative_view.LENSES]}

    def test_lead_needs_six_lenses(self):
        dp = {"narrative": {"lead": self.lead()}}
        self.assertTrue(narrative_view.lead_section(dp)["h2"].startswith("내러티브 — "))
        dp["narrative"]["lead"]["lenses"].pop()
        with self.assertRaises(ValueError):
            narrative_view.lead_section(dp)

    def test_narrative_and_ladder_come_first(self):
        d = {"sections": [{"h2": "① 주가", "blocks": []}, {"h2": "어닝콜 변화·컨센서스", "blocks": []}, {"h2": "② 실적", "blocks": []}],
             "summary": [{"q": "① 가격", "a": "x"}]}
        out = v2_to_report.merge_lead(d, {"h2": "내러티브 — 이야기", "blocks": []}, {"h2": "배수 사다리 — 2배가 되려면", "blocks": []},
                                      [{"q": "내러티브", "a": "n", "auto": True}, {"q": "2배", "a": "l", "auto": True}])
        self.assertEqual([s["h2"] for s in out["sections"]],
                         ["① 내러티브 — 이야기", "② 배수 사다리 — 2배가 되려면", "③ 주가", "어닝콜 변화·컨센서스", "④ 실적"])
        self.assertEqual([s["q"] for s in out["summary"]], ["① 내러티브", "② 2배", "③ 가격"])


class TestScrub(unittest.TestCase):
    def test_citations_removed_everywhere(self):
        d = {**BASE, "summary": [{"q": "q", "a": "경쟁 증설(Greenwood & Hanson 2015 — 과소평가)을 본다"}],
             "sections": [{"h2": "s", "blocks": [{"type": "p", "text": "희귀하다(Bessembinder 2018). CES 2026 발표"}]}],
             "sources": ["기저율: Bessembinder (2018) JFE 129(3) · Greenwood & Hanson (2015) QJE 130(1)", "Fiscal.ai 2026-10-30"]}
        h = report_html.render(d)
        for w in ("Greenwood", "Hanson", "Bessembinder", "JFE"):
            self.assertNotIn(w, h)
        self.assertIn("CES 2026", h)
        self.assertIn("Fiscal.ai 2026-10-30", h)
        self.assertNotIn("Greenwood", report_notion.render(d))

    def test_citation_outside_parens_fails(self):
        d = {**BASE, "sections": [{"h2": "s", "blocks": [{"type": "p", "text": "Bessembinder 2018은 희귀하다고 했다"}]}]}
        with self.assertRaises(ValueError):
            report_html.render(d)


class TestFigures(unittest.TestCase):
    def doc(self):
        return {**BASE, "sections": [{"h2": "a", "blocks": [chart("가", 9), chart("주가"), chart("배수")]},
                                     {"h2": "b", "blocks": [chart("매출"), chart("콜"), chart("서프라이즈"), chart("프리미엄"), chart("분포")]},
                                     {"h2": "c", "blocks": [chart("내포", 3), chart("리비전", 5), chart("분해", 8)]}]}

    def test_pins_keep_master_numbers(self):
        order = [b["chart"]["title"] for _, b in report_html.figures(self.doc())]
        self.assertEqual(order[:2], ["주가", "배수"])
        self.assertEqual((order[2], order[4], order[7], order[8]), ("내포", "리비전", "분해", "가"))

    def test_html_markdown_notion_share_numbers(self):
        d = self.doc()
        self.assertIn('그림 3 · 내포', report_html.render(d))
        self.assertEqual([c["title"] for c in report_md.charts_of(d)], [b["chart"]["title"] for _, b in report_html.figures(d)])
        self.assertIn("그림 3 · 내포", report_notion.render(d))


HIST = [["A", "2026-12-25", "2026-01-01", 1.0, 1], ["A", "2027-12-31", "2026-01-01", 2.0, 1],
        ["A", "2026-12-25", "2026-03-01", 2.0, 1], ["A", "2027-12-31", "2026-03-01", 4.0, 1],
        ["Q", "2027-03-26", "2026-03-01", 1.0, 1], ["Q", "2027-03-26", "2026-08-01", 1.5, 1]]


class TestRevision(unittest.TestCase):
    def test_annual_picks_up_later_quarter_change(self):
        h = rv.load_hist(HIST)
        self.assertEqual(rv.cy_value(h, 2027, date(2026, 7, 1)), 4.0)
        self.assertEqual(rv.cy_value(h, 2027, date(2026, 8, 2)), 4.5)   # 연간 4.0 + 분기 변화 0.5

    def test_calendarizes_non_december_year(self):
        h = rv.load_hist([["A", "2026-06-30", None, 2.0, 1], ["A", "2027-06-30", None, 4.0, 1]])
        self.assertAlmostEqual(rv.cy_value(h, 2026, date(2026, 1, 1)), 0.5 * 2.0 + 0.5 * 4.0)

    def test_decomposition_multiplies_back(self):
        h = rv.load_hist(HIST)
        px = {date(2026, 1, 15): 10.0, date(2026, 4, 15): 16.0, date(2026, 7, 15): 12.0, date(2026, 10, 29): 15.0}
        ev = [{"date": "2026-01-15", "kind": "실적", "tag": "4Q", "q": "4Q25", "session": "after"}, {"date": "2026-04-15", "kind": "실적", "tag": "1Q", "q": "1Q26", "session": "after"},
              {"date": "2026-07-15", "kind": "실적", "tag": "2Q", "q": "2Q26", "session": "after"}]
        rows = rv.decompose(h, ev, px)
        self.assertEqual([x["label"] for x in rows], ["4Q25 후", "1Q26 후", "2Q26 후"])
        self.assertEqual(rows[-1]["to"], date(2026, 10, 29))
        for x in rows:
            self.assertAlmostEqual((1 + x["price"]), (1 + x["rev"]) * (1 + x["rerate"]))

    def test_narrative_inside_earnings_window_is_not_measured(self):
        h = rv.load_hist(HIST)
        px = {date(2026, 2, 25): 10.0, date(2026, 2, 26): 11.0, date(2026, 3, 2): 12.0}
        ev = [{"date": "2026-02-25", "kind": "실적", "tag": "4Q", "session": "after"}, {"date": "2026-03-02", "kind": "내러티브", "tag": "증자", "session": "intraday"}]
        rows = rv.event_rows(h, ev, px, date(2026, 10, 29))
        self.assertEqual(rows[0]["rev"], 1.0)      # 2.0 → 4.0
        self.assertTrue(rows[1]["overlap"])
        self.assertIsNone(rows[1]["rev"])

    def test_blocks_draw_figure_five_and_eight(self):
        px = {date(2026, 1, 15): 10.0, date(2026, 4, 15): 16.0, date(2026, 10, 29): 15.0}
        dp = {"id": "x", "consensus": {"eps_history": {"rows": HIST}},
              "revision_events": [{"date": "2026-01-15", "kind": "실적", "tag": "4Q", "q": "4Q25", "session": "after"}, {"date": "2026-04-15", "kind": "실적", "tag": "1Q", "q": "1Q26", "session": "after"}]}
        with mock.patch.object(rv, "load_prices", return_value=px):
            bl = rv.blocks(dp)
        charts = [b["chart"] for b in bl if b["type"] == "chart"]
        self.assertEqual([c["pin"] for c in charts], [5, 8])
        self.assertIn("<svg", report_html.chart_revision(charts[0]))
        self.assertIn("①", report_html.chart_revision(charts[0]))
        self.assertTrue(report_md.standalone(charts[0]).startswith("<svg"))

    def test_old_datapack_falls_back(self):
        self.assertEqual(rv.blocks({"id": "x", "consensus": {}}), [])


if __name__ == "__main__":
    unittest.main()
