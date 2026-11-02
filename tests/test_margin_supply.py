"""리포트 마진 구조·공급망 병목 (마스터 지시 2026-11-02)"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import margin_view as mv  # noqa: E402
import report_layout as rl  # noqa: E402
import supply_view as sv  # noqa: E402

BOM = [{"item": "메모리", "share": 0.5, "basis": "티어다운", "source": "s1", "pass_through": 0.5, "why": "계약가"},
       {"item": "기판", "share": [0.1, 0.2], "basis": "추정", "source": "s2", "pass_through": "미확인", "why": "면적"},
       {"item": "조립", "share": 0.1, "basis": "공시", "source": "s3", "pass_through": 0.0, "why": "인건비"},
       {"item": "냉각", "share": "미확인", "basis": "추정", "source": "s4", "pass_through": "미확인", "why": "미확인"}]
MARGIN = {"as_of": "2026-09-30", "basis": "GAAP", "summary": "메모리가 마진을 정한다.",
          "periods": [{"period": "TTM 3Q25", "rev": 100, "cogs": 62, "rd": 10, "sga": 10}, {"period": "TTM 3Q26", "rev": 100, "cogs": 60, "rd": 10, "sga": 10}],
          "costs": [{"name": "원재료", "stage": "매출원가", "pct_rev": 0.5, "prior_pct": 0.52, "fixed": 0.0, "driver": "메모리 가격", "basis": "추정", "source": "10-K"},
                    {"name": "제조 경비", "stage": "매출원가", "pct_rev": 0.1, "prior_pct": "미확인", "fixed": 1.0, "driver": "가동률", "basis": "공시", "source": "10-K"},
                    {"name": "연구개발", "stage": "연구개발", "pct_rev": 0.1, "prior_pct": 0.1, "fixed": 1.0, "driver": "인력", "basis": "공시", "source": "10-K"},
                    {"name": "판관비", "stage": "판관비", "pct_rev": 0.1, "prior_pct": 0.1, "fixed": 0.5, "driver": "수수료", "basis": "공시", "source": "10-K"}],
          "products": [{"name": "서버", "rev_share": 0.6, "gpm": 0.4, "gpm_basis": "회사 전체 GPM", "bom": BOM}]}
LINK = {"item": "메모리", "critical": True, "suppliers": [{"name": "SK하이닉스", "role": "HBM", "share": 0.6, "status": "공시", "source": "10-K"}],
        "qualified": 1, "capacity": "부족", "lead_weeks": 60, "lead_normal": 20, "requal_months": 24, "top_share": 0.9, "region_share": 0.95, "secured": "현물",
        "why": "단일 공급원", "relief": "미확인", "source": "10-K"}
EASY = {**LINK, "item": "기판", "critical": False, "qualified": 4, "capacity": "여유", "lead_weeks": 10, "lead_normal": 10, "requal_months": 3, "top_share": 0.3, "region_share": 0.4, "secured": "내재화"}
DP = {"margin": MARGIN, "supply": {"as_of": "2026-09-30", "summary": "메모리가 막는다.", "links": [LINK, EASY]}}


class TestMarginMath(unittest.TestCase):
    def test_gpm_opm_from_income_statement(self):
        m = mv.margins(MARGIN["periods"][-1])
        self.assertAlmostEqual(m["gpm"], 0.4)
        self.assertAlmostEqual(m["opm"], 0.2)

    def test_no_pass_through_takes_full_hit(self):
        # 원가 60의 절반이 10% 오르면 3, GPM은 40 → 37
        self.assertAlmostEqual(mv.gpm_after(0.4, 0.5, 0.1, 0.0), -0.03)

    def test_full_pass_through_keeps_profit_but_dilutes_margin(self):
        move = mv.gpm_after(0.4, 0.5, 0.1, 1.0)
        self.assertAlmostEqual(move, 0.4 / 1.03 - 0.4)
        self.assertLess(move, 0)

    def test_company_effect_scales_with_revenue_share(self):
        self.assertAlmostEqual(mv.opm_after(0.2, 0.6, 0.4, 0.5, 0.1, 0.0), -0.018)

    def test_operating_leverage(self):
        lev = mv.leverage(0.2, MARGIN["costs"], 0.1)
        self.assertAlmostEqual(lev["variable"], 0.55)
        self.assertAlmostEqual(lev["move"], (0.2 + 0.1 * 0.45) / 1.1 - 0.2)

    def test_leverage_needs_every_fixed_share(self):
        costs = copy.deepcopy(MARGIN["costs"])
        costs[0]["fixed"] = "미확인"
        self.assertIsNone(mv.leverage(0.2, costs, 0.1))

    def test_range_and_unknown_shares(self):
        items = {r["item"]: r for r in mv.compute(DP)["items"]}
        self.assertAlmostEqual(items["기판"]["mid"], 0.15)
        self.assertEqual((items["기판"]["lo"], items["기판"]["hi"]), (0.1, 0.2))
        self.assertIsNone(items["냉각"]["opm_move"])


class TestMarginGate(unittest.TestCase):
    def bad(self, **change):
        mg = copy.deepcopy(MARGIN)
        mg.update(change)
        with self.assertRaises(ValueError):
            mv.check(mg)

    def test_good_passes(self):
        mv.check(MARGIN)

    def test_costs_must_tie_to_income_statement(self):
        costs = copy.deepcopy(MARGIN["costs"])
        costs[0]["pct_rev"] = 0.4
        self.bad(costs=costs)

    def test_needs_core_revenue_coverage(self):
        self.bad(products=[{**MARGIN["products"][0], "rev_share": 0.2}])

    def test_needs_three_known_bom_items(self):
        bom = copy.deepcopy(BOM)
        bom[0]["share"] = bom[2]["share"] = "미확인"
        self.bad(products=[{**MARGIN["products"][0], "bom": bom}])

    def test_bom_cannot_exceed_whole(self):
        bom = copy.deepcopy(BOM)
        bom[0]["share"] = 0.95
        self.bad(products=[{**MARGIN["products"][0], "bom": bom}])

    def test_blank_pass_through_stops(self):
        bom = copy.deepcopy(BOM)
        del bom[0]["pass_through"]
        self.bad(products=[{**MARGIN["products"][0], "bom": bom}])


class TestSupplyScore(unittest.TestCase):
    CFG = mv.config()["supply"]

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(self.CFG["weights"].values()), 1.0)

    def test_scale_ends(self):
        self.assertEqual(sv.scale(1.0, 1.0, 3.0), 10.0)
        self.assertEqual(sv.scale(9.0, 1.0, 3.0), 1.0)
        self.assertAlmostEqual(sv.scale(2.0, 1.0, 3.0), 5.5)

    def test_worst_and_best_links(self):
        c = sv.compute(DP)
        scores = {r["item"]: r["score"] for r in c["rows"]}
        self.assertAlmostEqual(scores["메모리"], 1.2)   # 현물 구매만 3점, 나머지 여섯 요인은 1점
        self.assertAlmostEqual(scores["기판"], 10.0)

    def test_weakest_link_outweighs_average(self):
        c = sv.compute(DP)
        expected = 0.6 * 1.2 + 0.4 * c["mean"]
        self.assertAlmostEqual(c["score"], expected)
        self.assertLess(c["score"], c["mean"])
        self.assertEqual((c["weakest"]["item"], c["grade"]), ("메모리", "병목 심각"))

    def test_cost_weight_drives_mean(self):
        c = sv.compute(DP)
        heavy, light = c["rows"][0]["cost_weight"], c["rows"][1]["cost_weight"]
        self.assertGreater(heavy, light)
        self.assertAlmostEqual(c["mean"], (heavy * 1.2 + light * 10) / (heavy + light))

    def test_unknown_factor_is_not_scored(self):
        f = sv.factors({**LINK, "capacity": "미확인", "region_share": "미확인"}, self.CFG)
        self.assertEqual(set(f), {"sources", "lead", "requal", "concentration", "secured"})

    def test_thin_link_is_left_out_and_counted(self):
        thin = {"item": "전원", "critical": True, "suppliers": LINK["suppliers"], "why": "w", "relief": "미확인", "source": "s", "qualified": 1}
        dp = {**DP, "supply": {**DP["supply"], "links": [LINK, EASY, thin]}}
        self.assertEqual([x["item"] for x in sv.compute(dp)["thin"]], ["전원"])
        self.assertIn("전원", str(sv.section(dp)["blocks"][0]))

    def test_tier_joins_bottleneck_and_margin(self):
        c = sv.compute(DP)
        self.assertEqual(sv.tier(c["rows"][0], c["cfg"], 0.005), "핵심 통제 품목")
        self.assertEqual(sv.tier(c["rows"][1], c["cfg"], 0.005), "가격 위험")


class TestSupplyGate(unittest.TestCase):
    def test_none_skips_section(self):
        self.assertIsNone(sv.section({"supply": {"none": "구독 소프트웨어"}}))

    def test_missing_material_stops(self):
        with self.assertRaises(SystemExit):
            sv.section({})
        with self.assertRaises(SystemExit):
            mv.section({})

    def test_supplier_needs_evidence_status(self):
        bad = copy.deepcopy(LINK)
        bad["suppliers"][0]["status"] = "들었다"
        with self.assertRaises(ValueError):
            sv.check({"as_of": "2026-09", "links": [bad, EASY]})

    def test_relief_is_required(self):
        bad = {k: v for k, v in LINK.items() if k != "relief"}
        with self.assertRaises(ValueError):
            sv.check({"as_of": "2026-09", "links": [bad, EASY]})


class TestReport(unittest.TestCase):
    def test_margin_section(self):
        sec = mv.section(DP)
        self.assertEqual(sec["h2"], "마진 구조")
        text = str(sec["blocks"])
        self.assertIn("GPM 40.0%, OPM 20.0%", text)
        self.assertIn("전가 0%로 계산", text)
        self.assertIn("10~20%", text)
        self.assertEqual(sec["_sources"], ["10-K", "s1", "s2", "s3", "s4"])

    def test_undecomposed_rest_is_shown(self):
        self.assertIn("미분해", str(mv.section(DP)["blocks"]))

    def test_same_item_adds_up_across_products(self):
        second = {**MARGIN["products"][0], "name": "스위치", "rev_share": 0.2}
        dp = {"margin": {**MARGIN, "products": [MARGIN["products"][0], second]}}
        items = mv.compute(dp)["items"]
        total = dict(mv.by_item(items))["메모리"]
        self.assertAlmostEqual(total, sum(r["opm_move"] for r in items if r["item"] == "메모리"))
        self.assertEqual(mv.top_item(dp)[0], "메모리")

    def test_tables_stay_narrow_for_phone(self):
        for sec in (mv.section(DP), sv.section(DP)):
            for b in sec["blocks"]:
                if b.get("type") == "table":
                    self.assertLessEqual(len(b["headers"]), 6 if "GPM에서" in b["title"] else 5, b["title"])

    def test_unknown_factor_stays_visible(self):
        text = str(sv.section({**DP, "supply": {**DP["supply"], "links": [{**LINK, "capacity": "미확인"}, EASY]}})["blocks"])
        self.assertIn("캐파 미확인", text)

    def test_supply_section(self):
        sec = sv.section(DP)
        self.assertEqual(sec["h2"], "공급망 병목")
        head = sec["blocks"][0]["text"]
        self.assertIn("/10", head)
        self.assertIn("가장 약한 고리는 메모리", head)
        self.assertIn("SK하이닉스", str(sec["blocks"]))

    def test_bottleneck_chart_lives_in_gallery_only(self):
        self.assertFalse([b for b in sv.section(DP)["blocks"] if b.get("type") == "chart"])
        c = sv.chart(DP)
        self.assertEqual(c["rows"][0]["label"], "공급망 신뢰성")
        self.assertEqual(c["rows"][1]["label"], "메모리")
        self.assertIsNone(sv.chart({"supply": {"none": "x"}}))

    def test_summary_item(self):
        s = sv.summary_item(DP)
        self.assertEqual(s["auto"], True)
        self.assertIn("메모리", s["a"])
        self.assertIn("/10", s["a"])

    def test_summary_without_supply_score(self):
        self.assertNotIn("/10", sv.summary_item({"margin": MARGIN, "supply": {"none": "x"}})["a"])

    def test_no_banned_words(self):
        body = str(mv.section(DP)) + str(sv.section(DP))
        self.assertEqual([w for w in rl.BANNED if w in body], [])


if __name__ == "__main__":
    unittest.main()
