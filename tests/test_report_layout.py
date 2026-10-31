"""텐배거 리포트 양식 3 (마스터 지시 2026-10-31)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
sys.path.insert(0, str(ROOT / "radar"))
import multiples  # noqa: E402
import report_html as rh  # noqa: E402
import report_layout as rl  # noqa: E402
import report_notion as rn  # noqa: E402
from units import fx_units, money_units  # noqa: E402

CFG = rl.config()
BASE = {"title": "t", "date": "2026-10-31", "ticker": "X", "company": "엑스", "biz": "사업"}


class TestRating(unittest.TestCase):
    def test_five_grades_by_rule(self):
        self.assertEqual(rl.rating(0.5, 3.5, 0.1, CFG), "Strong Buy")
        self.assertEqual(rl.rating(0.2, 2.0, -0.3, CFG), "Buy")
        self.assertEqual(rl.rating(0.05, 1.0, 0.0, CFG), "Neutral")
        self.assertEqual(rl.rating(-0.2, 0.5, -0.4, CFG), "Sell")
        self.assertEqual(rl.rating(-0.5, 0.2, -0.6, CFG), "Strong Sell")

    def test_dcf_blocks_top_grades(self):
        self.assertEqual(rl.rating(0.5, 3.5, -0.2, CFG), "Buy")     # DCF가 음수면 Strong Buy가 아니다
        self.assertEqual(rl.rating(0.5, 3.5, -0.6, CFG), "Neutral")

    def test_reward_risk(self):
        self.assertAlmostEqual(rl.reward_risk(100, 150, 75), 2.0)
        self.assertIsNone(rl.reward_risk(70, 150, 75))


class TestScenario(unittest.TestCase):
    def doc(self):
        return {"sections": [{"h2": "판단 시나리오", "blocks": [{"type": "chart", "chart": {"kind": "scenario", "cases": [
            {"name": "약세", "prob": 0.25, "eps": 2}, {"name": "기본", "prob": 0.5, "eps": 4}, {"name": "강세", "prob": 0.25, "eps": 5}]}}]}]}

    def test_engine_prices_cases_with_selected_multiple(self):
        s = rl.scenario_build(self.doc(), {"profile": {"price": 100}}, {}, {"value": 30, "basis": "pe_fwd"}, 1.0)
        self.assertEqual((s["bear"], s["base"], s["bull"]), (45.0, 120.0, 187.5))
        self.assertAlmostEqual(s["weighted"], 118.1, 1)
        self.assertAlmostEqual(s["rr"], 87.5 / 55)

    def test_rejects_bad_probabilities(self):
        d = self.doc()
        d["sections"][0]["blocks"][0]["chart"]["cases"][0]["prob"] = 0.9
        with self.assertRaises(SystemExit):
            rl.scenario_build(d, {"profile": {"price": 100}}, {}, {"value": 30, "basis": "pe_fwd"}, 1.0)

    def test_upside_by_support_level(self):
        c = rl.upside_chart({"price": 100, "weighted": 120}, [{"mid": 80, "srcs": ["주봉 피보 50%", "50주선"]}])
        self.assertEqual(c["title"], "주가별 업사이드")
        self.assertEqual(c["rows"][0]["bars"][0]["value"], 20.0)
        self.assertEqual(c["rows"][1]["bars"][0]["value"], 50.0)
        self.assertIn("외 1", c["rows"][1]["label"])


class TestMultiple(unittest.TestCase):
    def mm(self):
        return {"basis": "pe_fwd", "peers": [{"pe_fwd": 20.0}, {"pe_fwd": 25.0}, {"pe_fwd": 30.0}],
                "horizons": [{"h": 1, "key": "pe_fwd", "label": "Fwd 1Y P/E", "current": 21.0, "peer_range": {"p50": 25.0}, "rational": {"p50": 35.0}}]}

    def test_steps_from_peer_median(self):
        dp = {"moat": {"items": [{"kind": "a에 따른 b", "verdict": "강함"}]}, "narrative": {"stage": "확산"}, "multiple_view": {"adj": -0.1, "why": "사이클"}}
        s = multiples.select_multiple(self.mm(), dp, CFG["multiple_select"])
        self.assertAlmostEqual(s["value"], 25 * (1 + 0.2 + 0.04 + 0.05 - 0.1))
        self.assertEqual(s["rows"][-1][0], "**선정**")

    def test_stays_inside_peer_range(self):
        dp = {"multiple_view": {"adj": -0.9, "why": "x"}, "narrative": {"stage": "붕괴"}}
        s = multiples.select_multiple(self.mm(), dp, CFG["multiple_select"])
        self.assertEqual(s["value"], 20.0)


class TestNotation(unittest.TestCase):
    def test_currencies(self):
        self.assertEqual(fx_units("163억 엔"), "¥16.3B")
        self.assertEqual(fx_units("3억 유로"), "€300M")
        self.assertEqual(fx_units("2,000만 파운드"), "£20M")
        self.assertEqual(fx_units("100~120억 엔"), "¥10~12B")
        self.assertEqual(fx_units("1조 2,000억 원"), "₩1.2T")
        self.assertEqual(money_units(fx_units("엔비디아 3억 달러")), "엔비디아 $300M")

    def test_quarter_label(self):
        self.assertEqual(rh.quarter_text("2026Q3과 26Q3, 3Q26"), "3Q26과 3Q26, 3Q26")
        self.assertEqual(rh.quarter_text("https://x.com/2026Q3"), "https://x.com/2026Q3")

    def test_finance_words_not_glossed_tech_is(self):
        d = {**BASE, "format": 3, "verdict": {"view": "CAGR·OPM·EPS·컨센서스·가이던스와 CPO, Triton"}, "terms": {"Triton": "광 시험 장비"}}
        h = rh.render(d)
        for w in ("CAGR(", "OPM(", "컨센서스(", "가이던스("):
            self.assertNotIn(w, h)
        self.assertIn("CPO(칩 옆에", h)
        self.assertIn("Triton(광 시험 장비)", h)


class TestRender(unittest.TestCase):
    def doc(self):
        return {**BASE, "format": 3, "verdict": {"view": "판단", "rating": "Buy"},
                "tiles": [{"k": "구매등급", "v": "Buy", "sub": "s"}],
                "summary": [{"q": "질문", "a": "답"}],
                "gallery": [{"kind": "bars", "title": "멀티플 프리미엄", "categories": ["a"], "series": [{"name": "x", "values": [1]}]}],
                "sections": [{"h2": "해자", "blocks": [{"type": "boxes", "items": [{"title": "b", "tag": "강함", "lines": [["근거", "내용"]]}]}]}]}

    def test_order_no_figure_numbers(self):
        h = rh.render(self.doc())
        self.assertLess(h.index("Chiip View"), h.index('class="dash"'))
        self.assertLess(h.index('class="dash"'), h.index("한 장 요약"))
        self.assertLess(h.index("한 장 요약"), h.index("한눈에 보기"))
        self.assertLess(h.index("한눈에 보기"), h.index("해자"))
        self.assertNotIn("그림 1", h)
        self.assertNotIn("컨빅션", h)
        self.assertIn('class="bx"', h)

    def test_notion_has_boxes_and_dashboard(self):
        out = rn.render(self.doc())
        self.assertIn("## 대시보드", out)
        self.assertIn("> **근거:** 내용", out)
        self.assertNotIn("컨빅션", out)

    def test_actual_and_estimate_colors(self):
        c = {"kind": "actest", "panels": [{"name": "매출", "categories": ["3Q26", "4Q26"], "actual": [280, None], "est": [277, 285]}]}
        s = rh.chart_actest(c)
        self.assertIn("var(--c)", s)
        self.assertIn("var(--e)", s)
        self.assertIn("실적", s)

    def test_candle_draws_moving_averages(self):
        c = {"bars": [["2026-10-01", 10, 11, 9, 10.5], ["2026-10-02", 10.5, 12, 10, 11]], "lines": [{"name": "50일선", "color": "c", "points": [["2026-10-01", 10], ["2026-10-02", 10.5]]}], "legend": [{"name": "50일선", "color": "c"}]}
        s = rh.chart_candle(c)
        self.assertIn("polyline", s)
        self.assertIn("50일선", s)


class TestSupports(unittest.TestCase):
    def bars(self, n=260):
        return [{"date": f"2026-{1 + i // 30:02d}-{1 + i % 28:02d}", "o": 50 + i * 0.5, "h": 51 + i * 0.5, "l": 49 + i * 0.5, "c": 50 + i * 0.5, "v": 1000} for i in range(n)]

    def test_supports_sit_below_price(self):
        import levels
        out = levels.supports(self.bars())
        self.assertTrue(out["zones"])
        self.assertTrue(all(z["mid"] < out["price"] for z in out["zones"]))
        kinds = " ".join(x["src"] for v in out["frames"].values() for x in v)
        self.assertIn("선", kinds)
        self.assertIn("피보", kinds)


class TestPipelineChart(unittest.TestCase):
    def test_progress_chart_shows_unknown(self):
        s = rh.chart_progress({"rows": [{"label": "A", "total": 2.0, "pct": 0.5, "size": "$2B", "status": "확정"}, {"label": "B", "total": None, "pct": None, "size": "미확인", "status": "파이프라인"}]})
        self.assertIn("진척 50%", s)
        self.assertIn("진척 미확인", s)
        self.assertIn("stroke-dasharray", s)

    def test_section_drops_profit_table(self):
        import pipeline_view as pv
        dp = {"unit": "B$", "pipeline": {"as_of": "2026-09-30", "items": [{"name": "A", "status": "확정", "total": 1.0, "progress": 0.5, "margin": 0.1, "margin_basis": "x", "blockers": ["y"], "source": "z"}]}}
        sec = pv.section3(dp)
        titles = [b.get("title") for b in sec["blocks"]]
        self.assertNotIn("진척도별 수익", titles)
        self.assertTrue(any(b.get("type") == "chart" for b in sec["blocks"]))


class TestLeaders(unittest.TestCase):
    def dp(self):
        return {"financials": {"rev_ttm": 10.0}, "leaders": {"people": [{"name": "A", "role": "CEO", "since": "2020", "profile": "p", "business": "b", "political": "미확인", "alumni": "미확인", "social": "미확인", "source": "위임장"}],
                                                             "value": [{"network": "정계", "link": "국방부", "strength": 4, "exposure": 5.0, "basis": "매출", "evidence": "10-K"}]}}

    def test_weighted_exposure(self):
        import leader_view as lv
        sec = lv.report_section(self.dp(), {}, lambda x: f"${x:.1f}B")
        t = next(b for b in sec["blocks"] if b.get("type") == "table")
        self.assertEqual(t["rows"][0][3:5], ["$4.0B", "40%"])
        self.assertTrue(any("입증" in str(b.get("text")) for b in sec["blocks"]))

    def test_missing_field_stops(self):
        import leader_view as lv
        d = self.dp()
        del d["leaders"]["people"][0]["social"]
        with self.assertRaises(ValueError):
            lv.report_section(d, {}, str)


class TestAssemble(unittest.TestCase):
    def test_unknown_section_stops(self):
        with self.assertRaises(SystemExit):
            rl.assemble({"sections": [{"h2": "주가와 배수"}]}, {}, {}, {}, {}, {}, {}, None, {}, "x")

    def test_moat_is_company_specific(self):
        with self.assertRaises(SystemExit):
            rl.moat_section({"moat": {"items": [{"kind": "보안 인가 인력", "claim": "x", "evidence": "y"}]}})
        sec = rl.moat_section({"moat": {"items": [{"kind": k, "claim": "x", "evidence": "y", "verdict": "보통"} for k in ("보안 인가 인력", "전환 비용")]}})
        self.assertEqual(sec["h2"], "해자")

    def test_product_name_needs_gloss(self):
        dp = {"narrative": {"lead": {"products": [{"name": "Optimus 플랫폼"}]}}}
        d = {"ticker": "X", "verdict": {"view": "x"}, "summary": [], "sections": []}
        self.assertEqual(rl.unglossed(d, dp), ["Optimus"])
        self.assertEqual(rl.unglossed(d, {**dp, "terms": {"Optimus": "풀이"}}), [])

    def test_unglossed_abbreviation_is_caught(self):
        d = {"ticker": "X", "verdict": {"view": "XYZQ 기술과 EPS"}, "summary": [], "sections": []}
        self.assertEqual(rl.unglossed(d, {}), ["XYZQ"])
        self.assertEqual(rl.unglossed(d, {"terms": {"XYZQ": "풀이"}}), [])


if __name__ == "__main__":
    unittest.main()
