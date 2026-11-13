"""리포트 '자산 구성과 ROIC' 절 (마스터 지시 2026-11-13, ADR-021)"""
import copy
import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import asset_roic_view as av  # noqa: E402
import report_html  # noqa: E402

LTH = json.loads((ROOT / "tests" / "fixtures" / "asset_roic_lth.json").read_text(encoding="utf-8"))


class TestLives(unittest.TestCase):
    def test_holt_style_life_formulas(self):
        lv, band = av.lives(LTH)
        x = lv[0]
        # 상각 대상 = 5563.4 − 토지 431.5 − 건설중 555.1 = 4576.9, 연 감가 292.7
        self.assertAlmostEqual(x["dep_gross"], 5563.449 - 431.467 - 555.09, places=3)
        self.assertAlmostEqual(x["avg"], x["dep_gross"] / 292.7)
        self.assertAlmostEqual(x["age"], 1930.22 / 292.7)
        self.assertAlmostEqual(x["remain"], x["avg"] - x["age"])   # 평균 = 경과 + 잔여
        self.assertTrue(band["lo"] < band["mid"] < band["hi"])

    def test_quarter_rate_uses_average_base_and_annualizes(self):
        rows = av.dep_rates(LTH)
        last = rows[-1]
        self.assertEqual(last["q"], "3Q26")
        self.assertEqual(last["basis"], "순액")   # 분기 총액이 없으면 순액이라고 밝힌다
        self.assertAlmostEqual(last["rate_q"], 85.013 / ((3811.994 + 3955.367) / 2))
        self.assertAlmostEqual(last["rate_y"], last["rate_q"] * 4)
        self.assertEqual(len(rows), 8)

    def test_dep_shift_counterfactual(self):
        a = copy.deepcopy(LTH)
        for q in a["quarters"][-4:]:
            q["da"] *= 0.8   # 최근 4분기 감가를 20% 낮추면 경고가 뜨고 이익 효과가 양수
        s = av.dep_shift(av.dep_rates(a), 572.0, av.config())
        self.assertTrue(s["flag"])
        self.assertGreater(s["boost"], 0)
        calm = av.dep_shift(av.dep_rates(LTH), 572.0, av.config())
        self.assertFalse(calm["flag"])


class TestRoic(unittest.TestCase):
    def test_nopat_and_versions(self):
        p1 = av.roic(LTH)[0]
        lease = (2808.436 + 2612.214) / 2 * 0.0928
        self.assertAlmostEqual(p1["nopat"], (572.077 + 1.1 + lease) * 0.75)
        self.assertTrue(p1["avg"])
        self.assertGreater(p1["roic_excl"], p1["roic_incl"])   # 영업권을 빼면 분모가 작다
        self.assertAlmostEqual(p1["roic_incl"], p1["margin"] * p1["rev"] / p1["ic_incl"])   # ROIC = 마진 × 회전율
        self.assertAlmostEqual(p1["cap"]["goodwill"], 1235.359 + 3.3)   # 손상 누계를 되더한다

    def test_lmdi_sums_exactly(self):
        p1, p0 = av.roic(LTH)
        for ver in ("incl", "excl"):
            dec = av.lmdi(p1, p0, ver)
            self.assertAlmostEqual(sum(v for _, v in dec["parts"]), dec["to"] - dec["from"], places=12)

    def test_lmdi_refuses_nonpositive(self):
        a = copy.deepcopy(LTH)
        a["roic"]["ebit"] = [-500.0, 438.739]
        a["roic"]["lease_rate"] = None
        p1, p0 = av.roic(a)
        self.assertIsNone(av.lmdi(p1, p0))

    def test_item_without_is_consistent(self):
        p1 = av.roic(LTH)[0]
        for x in av.item_rows(p1):
            self.assertAlmostEqual(x["without"], p1["nopat"] / (p1["ic_incl"] - x["cap"]))
        self.assertAlmostEqual(sum(x["share"] for x in av.item_rows(p1)), 1.0)


class TestCapitalize(unittest.TestCase):
    def test_damodaran_straight_line(self):
        # 매년 100, 5년 상각 → 자산 = 100 × (1 + .8 + .6 + .4 + .2) = 300, 상각 = 지난 5년 × 20 = 100
        c = av.capitalize([[y, 100.0] for y in range(2015, 2026)], 5)
        self.assertAlmostEqual(c["asset"], 300.0)
        self.assertAlmostEqual(c["amort"], 100.0)
        self.assertFalse(c["short"])
        self.assertTrue(av.capitalize([[2024, 100.0], [2025, 100.0]], 5)["short"])

    def test_flat_spend_leaves_nopat_unchanged(self):
        a = copy.deepcopy(LTH)
        a["intangible_cap"] = {"sga": [[y, 100.0] for y in range(2015, 2026)]}
        p1 = av.roic(a)[0]
        v = av.cap_version(a, p1, av.config())
        self.assertAlmostEqual(v["delta"], 0.0)   # 투자 = 상각이면 NOPAT은 그대로, 분모만 커진다
        self.assertLess(v["roic"], p1["roic_incl"])


class TestSection(unittest.TestCase):
    def test_absent_data_no_section(self):
        self.assertIsNone(av.section({}))
        self.assertIsNone(av.section({"assets": {"none": "공시 없음"}}))

    def test_lth_section_renders(self):
        s = av.section({"assets": LTH}, 0.09)
        self.assertEqual(s["h2"], "자산 구성과 ROIC")
        kinds = [b["type"] for b in s["blocks"]]
        self.assertEqual(kinds[0], "hl")
        titles = [b.get("title", "") for b in s["blocks"]]
        for t in ("항목별 가치", "내용연수 산식", "분기 감가 비율", "회전율과 ROIC 기여", "ROIC 세 가지 판", "1년 변화 분해", "무형 자본화 가정별"):
            self.assertTrue(any(t in x for x in titles), t)
        for b in s["blocks"]:
            if b["type"] == "chart":
                self.assertTrue(report_html.CHARTS[b["chart"]["kind"]](b["chart"]).__contains__("<svg"))
        body = json.dumps(s, ensure_ascii=False)
        self.assertNotIn("nan", body.lower().replace("finance", ""))
        self.assertNotIn("PP&E", body)   # 풀이 없는 약자 금지 — 유형자산으로 쓴다

    def test_layout_wires_section_after_margin(self):
        src = (ROOT / "scripts" / "tenbagger" / "report_layout.py").read_text(encoding="utf-8")
        self.assertIn("for part in (margin_sec, asset_sec, supply_sec, capacity_sec)", src)


if __name__ == "__main__":
    unittest.main()


def _facts():
    """asset_pack 시험용 최소 SEC 회사 사실 묶음(백만 달러 × 1e6)"""
    q_ends = ["2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30", "2026-09-30"]
    starts = {"03-31": "01-01", "06-30": "04-01", "09-30": "07-01", "12-31": "10-01"}

    def dur(vals):
        out = []
        for e, v in zip(q_ends, vals):
            if e.endswith("12-31"):   # 4분기는 연간으로만 — asset_pack이 연간 − 1~3분기로 만든다
                y = e[:4]
                qs = [x for x, e2 in zip(vals, q_ends) if e2[:4] == y and not e2.endswith("12-31")]
                out.append({"start": f"{y}-01-01", "end": e, "val": (sum(qs) + v) * 1e6})
            else:
                out.append({"start": f"{e[:4]}-{starts[e[5:]]}", "end": e, "val": v * 1e6})
        return {"units": {"USD": out}}

    def inst(vals):
        return {"units": {"USD": [{"end": e, "val": v * 1e6} for e, v in zip(q_ends, vals)]}}
    g = {"RevenueFromContractWithCustomerExcludingAssessedTax": dur([100] * 9), "OperatingIncomeLoss": dur([10] * 9),
         "DepreciationDepletionAndAmortization": dur([5] * 9), "PropertyPlantAndEquipmentNet": inst([400] * 9),
         "OperatingLeaseRightOfUseAsset": inst([200] * 9), "Goodwill": inst([50] * 9), "AccountsReceivableNetCurrent": inst([20] * 9),
         "AccountsPayableCurrent": inst([30] * 9),
         "OperatingLeaseWeightedAverageDiscountRatePercent": {"units": {"pure": [{"end": "2025-12-31", "val": 0.07}]}}}
    return {"facts": {"us-gaap": g}}


class TestAssetPack(unittest.TestCase):
    def test_build_from_facts_marks_missing(self):
        import asset_pack
        a = asset_pack.build(_facts(), 0.21)
        self.assertEqual(a["roic"]["rev"], [400.0, 400.0])
        self.assertEqual(a["roic"]["lease_rate"], 0.07)
        self.assertEqual(a["roic"]["capital"]["nwc"][0], -10.0)
        qs = {x["q"]: x for x in a["quarters"]}
        self.assertNotIn("4Q24", qs)   # 2024년 1·2분기가 없으면 4분기를 만들지 않는다
        self.assertAlmostEqual(qs["4Q25"]["da"], 5.0)   # 연간 − 1~3분기
        self.assertIn("운영리스 부채", a["missing"])
        s = av.section({"assets": a}, 0.09)   # 항목 주석이 없어도 절은 나온다
        self.assertTrue(any("미공시" in (b.get("text") or "") for b in s["blocks"]))

    def test_merge_keeps_model_rows(self):
        import asset_pack
        old = {"ppe": [{"name": "토지", "kind": "land", "gross": [1, 1]}], "roic": None, "missing": ["유형자산 항목별 총액·내용연수(10-K 주석에서 모델이 채움)"]}
        new = asset_pack.build(_facts(), 0.21)
        m = asset_pack.merge(old, new)
        self.assertEqual(m["ppe"][0]["name"], "토지")
        self.assertIsNotNone(m["roic"])
        self.assertFalse(any(x.startswith("유형자산 항목별") for x in m["missing"]))


class TestRoicCard(unittest.TestCase):
    def test_one_roic_picture_in_gallery(self):
        s = av.section({"assets": LTH}, 0.09)
        charts = [b["chart"] for b in s["blocks"] if b["type"] == "chart"]
        self.assertEqual([c["kind"] for c in charts], ["line", "roic"])   # 감가 비율 선 + ROIC 한 장
        c = charts[1]
        self.assertEqual(c["wacc"], 9.0)
        self.assertEqual([r["label"] for r in c["rates"]][:2], ["ROIC 영업권 포함", "ROIC 영업권 제외"])
        svg = report_html.CHARTS["roic"](c)
        self.assertIn("WACC 9.0%", svg)
        self.assertIn("−$", svg)   # 음수 운전자본은 '차감'
        self.assertIn("차감", svg)


class TestMarginTrim(unittest.TestCase):
    def test_duplicate_tables_removed_when_bridge_exists(self):
        import margin_view
        dp = json.loads((ROOT / "knowledge" / "models" / "companies" / "us-cbrs" / "datapack.json").read_text(encoding="utf-8"))
        titles = [b.get("title", "") for b in margin_view.section(dp)["blocks"]]
        self.assertFalse(any(t.startswith("GPM·OPM 최근 4개 분기") for t in titles))
        import cost_bridge_view
        has_bridge = bool(cost_bridge_view.compute(dp))
        self.assertEqual(any(t.startswith("마진을 결정하는 비용 요인") for t in titles), not has_bridge)


class TestCheckFlag(unittest.TestCase):
    def test_missing_assets_flagged_outside_score(self):
        sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
        import datapack_check
        p = datapack_check.load("us-cbrs")
        p.pop("assets", None)
        r = datapack_check.check(p)
        c = next(x for x in r["checks"] if x["name"] == "자산 구성(assets)")
        self.assertEqual(c["status"], "경고")
        p["assets"] = LTH
        r2 = datapack_check.check(p)
        self.assertEqual(r2["score"], r["score"])   # 점수에는 넣지 않는다
        self.assertEqual(next(x for x in r2["checks"] if x["name"] == "자산 구성(assets)")["status"], "통과")


class TestLineTap(unittest.TestCase):
    def test_points_show_value_on_tap(self):
        c = {"kind": "line", "title": "분기 비용 비중 추이(매출 대비, 공시)", "unit": "%",
             "series": [{"name": "매출원가", "color": "c", "points": [["2025-09", 52.1], ["2025-12", 51.4]]},
                        {"name": "영업이익률", "color": "a", "points": [["2025-09", 17.3], ["2025-12", 17.7]]}]}
        out = report_html.CHARTS["line"](c)
        self.assertEqual(out.count('class="lp"'), 4)
        self.assertIn('data-n="매출원가" data-x="2025-09" data-v="52.1%"', out)
        self.assertIn('class="cinfo"', out)   # 누른 값이 뜨는 칸
        self.assertIn("closest('.lp')", report_html.FIT_JS)
        neg = report_html.CHARTS["line"]({"kind": "line", "unit": "%", "series": [{"name": "변화", "points": [["a", -1.5], ["b", 2.0]]}]})
        self.assertNotIn('data-v="<', neg)   # 속성 값에 색칠 태그가 들어가지 않는다
