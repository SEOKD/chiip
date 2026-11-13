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
        s, r = av.section({"assets": LTH}, 0.09), av.roic_section({"assets": LTH}, 0.09)   # 자산 구성과 ROIC는 두 절(마스터 지시 2026-11-14)
        self.assertEqual((s["h2"], r["h2"]), ("자산 구성", "ROIC"))
        self.assertEqual((s["blocks"][0]["type"], r["blocks"][0]["type"]), ("hl", "hl"))
        st = [b.get("title", "") for b in s["blocks"]]
        rt = [b.get("title", "") for b in r["blocks"]]
        for t in ("항목별 가치", "내용연수 산식", "분기 감가 비율"):
            self.assertTrue(any(t in x for x in st), t)
        for t in ("회전율과 ROIC 기여", "ROIC 세 가지 판", "1년 변화 분해", "무형 자본화 가정별"):
            self.assertTrue(any(t in x for x in rt), t)
            self.assertFalse(any(t in x for x in st), t)   # 세부 설명도 분리
        for b in s["blocks"] + r["blocks"]:
            if b["type"] == "chart":
                self.assertTrue(report_html.CHARTS[b["chart"]["kind"]](b["chart"]).__contains__("<svg"))
        body = json.dumps([s, r], ensure_ascii=False)
        self.assertNotIn("nan", body.lower().replace("finance", ""))
        self.assertNotIn("PP&E", body)   # 풀이 없는 약자 금지 — 유형자산으로 쓴다

    def test_layout_wires_section_after_margin(self):
        src = (ROOT / "scripts" / "tenbagger" / "report_layout.py").read_text(encoding="utf-8")
        self.assertIn("for part in (margin_sec, asset_sec, roic_sec, supply_sec, capacity_sec)", src)


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
        s, r = av.section({"assets": LTH}, 0.09), av.roic_section({"assets": LTH}, 0.09)
        sc = [b["chart"] for b in s["blocks"] if b["type"] == "chart"]
        self.assertEqual([c["kind"] for c in sc], ["roic"])   # 분기 이력이 없으면 자산 구성 한 장(구성만)
        self.assertEqual(sc[0]["rates"], [])
        self.assertIn("<svg", report_html.CHARTS["roic"](sc[0]))
        charts = [b["chart"] for b in r["blocks"] if b["type"] == "chart"]
        self.assertEqual([c["kind"] for c in charts], ["roic", "line"])   # 이력 없는 옛 datapack: 두 기간 판 한 장 → 감가 비율 선(ROIC 뒤)
        c = charts[0]
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


class TestSelfWords(unittest.TestCase):
    def test_license_phrase_removed(self):
        for a, b in (("3Q26 어닝콜(2026-11-04, 요지만 자기 말로)", "3Q26 어닝콜(2026-11-04)"), ("2Q 콜(2026-11-12) — 요지만 자기 말로", "2Q 콜(2026-11-12)"),
                     ("어닝콜 요지만 자기 말로, 매출 상향", "어닝콜 매출 상향")):
            self.assertEqual(report_html._scrub_text(a), b)
        d = report_html.scrub({"sections": [{"h2": "해자", "blocks": [{"type": "boxes", "items": [{"title": "x", "lines": [["증거", "3Q26 어닝콜(2026-11-04, 요지만 자기 말로)"]]}]}]}]})
        self.assertNotIn("자기 말로", json.dumps(d, ensure_ascii=False))


def _hist(n=16, grow=0.03):
    """분기 이력 — 매출이 분기 3%씩 늘고 잔액은 매출에 비례(회전 일수 일정)"""
    rows = []
    for i in range(n):
        rev = 1000 * (1 + grow) ** i
        y, q = 2022 + (i + 3) // 4, (i + 3) % 4 + 1
        end = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[q]
        rows.append({"q": f"{q}Q{str(y)[2:]}", "end": f"{y}-{end}", "rev": rev, "ebit": rev * 0.2, "cogs": rev * 0.5, "capex": rev * 0.08, "da": 40.0 + i, "amort": 2.0,
                     "bal": {"ar": rev * 0.8, "inv": rev * 0.5 * 1.2, "prepaid": rev * 0.1, "ap": rev * 0.5 * 0.6, "accrued": rev * 0.3, "deferred_rev": rev * 0.2,
                             "ppe": 2000 + 30 * i, "rou": 300.0, "goodwill": 500.0, "intangibles": 100.0 - 2 * i, "other": -10.0}, "lease": 320.0})
    return rows


def _assets_hist():
    return {"unit": "$M", "hist": _hist(), "roic": {"tax_rate": 0.2, "lease_rate": 0.05, "acq_amort": [8.0, 8.0], "impairment_cum": 0}}


def _dp_cons(a):
    return {"assets": a, "sbc_pct_rev": 0.02,
            "consensus": {"quarters_est": {"2027Q1": 1.70, "2026Q4": 1.65, "2027Q2": 1.75, "2027Q3": 1.80}, "ebit_margin": {"FY2026": 0.24, "FY2027": 0.25}, "margin_basis": "non_gaap"}}


class TestHistoryForecast(unittest.TestCase):
    """자산 구성 12개 분기 변화율·ROIC 12개 분기 추이·다음 4개 분기 추정(마스터 지시 2026-11-14)"""

    def test_series_prefers_concept_with_latest_values(self):
        import asset_pack
        old = {"units": {"USD": [{"start": "2020-01-01", "end": "2020-03-31", "val": 1e6}]}}
        new = {"units": {"USD": [{"start": "2026-04-01", "end": "2026-06-30", "val": 9e6}, {"start": "2020-01-01", "end": "2020-03-31", "val": 2e6}]}}
        s, c = asset_pack.series({"facts": {"us-gaap": {"Revenues": old, "RevenueFromContractWithCustomerExcludingAssessedTax": new}}}, "rev", "q")
        self.assertEqual(c, "RevenueFromContractWithCustomerExcludingAssessedTax")   # AMAT: 'Revenues'가 2021년에 끝나 TTM 1Q21이 나왔다
        self.assertEqual(max(s), "2026-06-30")
        self.assertEqual(s["2020-03-31"], 2.0)   # 같은 분기는 최근 개념 값

    def test_ytd_cash_flow_differenced(self):
        import asset_pack
        rows = [{"start": "2025-10-27", "end": "2026-01-25", "val": 100e6}, {"start": "2025-10-27", "end": "2026-04-26", "val": 230e6},
                {"start": "2025-10-27", "end": "2026-07-26", "val": 380e6}]
        s, _ = asset_pack.series({"facts": {"us-gaap": {"PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": rows}}}}}, "capex", "q")
        self.assertEqual([s[k] for k in sorted(s)], [100.0, 130.0, 150.0])   # 6·9개월 누적 − 앞 누적

    def test_forecast_four_quarters_from_consensus_and_drivers(self):
        a = _assets_hist()
        F, d = av.forecast(a, _dp_cons(a))
        self.assertEqual(len(F), 4)
        self.assertEqual([x["q"] for x in F], ["4Q26", "1Q27", "2Q27", "3Q27"])
        self.assertAlmostEqual(F[0]["rev"], 1650.0)   # 십억 단위 컨센서스 → 백만, 키 순서대로(2026Q4 먼저)
        self.assertAlmostEqual(F[0]["ebita"], 1650 * (0.24 - 0.02))   # 조정 마진 − 주식보상
        self.assertAlmostEqual(F[1]["ebita"], 1700 * (0.25 - 0.02))
        self.assertAlmostEqual(d["days"]["ar"], 0.8 * 91.25, places=6)   # 매출채권 일수
        self.assertAlmostEqual(F[0]["bal"]["ar"], 0.8 * 1650, places=6)
        self.assertAlmostEqual(F[0]["bal"]["inv"], 1.2 * 1650 * 0.5, places=6)   # 재고는 매출원가 기준
        last = a["hist"][-1]["bal"]
        self.assertAlmostEqual(F[0]["bal"]["ppe"], last["ppe"] + F[0]["capex"] - F[0]["dep"] + d["ppe_resid"])   # 이월 + 처분·재분류 잔차
        H = a["hist"]
        exp = sum(H[i]["bal"]["ppe"] - H[i - 1]["bal"]["ppe"] - H[i]["capex"] + (H[i]["da"] - H[i]["amort"]) for i in range(-4, 0)) / 4
        self.assertAlmostEqual(d["ppe_resid"], exp)   # 유형자산 이월
        self.assertEqual(F[-1]["bal"]["goodwill"], 500.0)
        self.assertAlmostEqual(F[0]["bal"]["intangibles"], last["intangibles"] - 2.0)

    def test_reported_quarter_before_10q_uses_actuals(self):
        a = _assets_hist()
        dp = _dp_cons(a)
        dp["quarters_hist"] = {"q": [{"period": "2026-12-31", "rev": 1.6e9, "op": 0.33e9, "cogs": 0.8e9}]}
        F, _ = av.forecast(a, dp)
        self.assertEqual(F[0]["q"], "4Q26")
        self.assertAlmostEqual(F[0]["rev"], 1600.0)
        self.assertAlmostEqual(F[0]["ebita"], 330.0 + 2.0)   # 발표 영업이익 + 인수 무형 상각
        self.assertIn("발표 실적", F[0]["est"])
        self.assertAlmostEqual(F[1]["rev"], 1650.0)   # 다음부터 컨센서스

    def test_roic_path_twelve_plus_four(self):
        a = _assets_hist()
        F, _ = av.forecast(a, _dp_cons(a))
        path = av.roic_path(a, a["hist"] + F)
        act = [x for x in path if not x["est"]]
        self.assertEqual((len(act), len(path) - len(act)), (12, 4))
        x = act[-1]
        H = a["hist"]
        ttm = sum(r["rev"] for r in H[-4:])
        ebita = sum(r["ebit"] + r["amort"] for r in H[-4:]) + (320 + 320) / 2 * 0.05
        ic = (sum(av.cap_of(H[-1]).values()) + sum(av.cap_of(H[-5]).values())) / 2
        self.assertAlmostEqual(x["rev"], ttm)
        self.assertAlmostEqual(x["roic_incl"], ebita * 0.8 / ic)   # TTM NOPAT ÷ 평균 투하자본(이번·4개 분기 전)

    def test_sections_charts_with_history(self):
        a = _assets_hist()
        dp = _dp_cons(a)
        s, r = av.section(dp, 0.1), av.roic_section(dp, 0.1)
        sc = [b["chart"] for b in s["blocks"] if b["type"] == "chart"]
        self.assertEqual([c["kind"] for c in sc], ["roic", "line"])   # 최근 분기 구성 → 자산별 변화율
        self.assertIn("3Q26 분기말", sc[0]["title"])
        ch = sc[1]
        self.assertEqual(ch["est_from"], "4Q26")
        self.assertEqual(len(ch["series"][0]["points"]), 16)   # 12개 분기 + 4개 분기 추정
        self.assertEqual(ch["series"][0]["points"][0][1], 0.0)
        rc = [b["chart"] for b in r["blocks"] if b["type"] == "chart"]
        self.assertTrue(rc[0]["title"].startswith("ROIC 추이"))
        self.assertEqual(rc[0]["est_from"], "4Q26")
        self.assertEqual(len(rc[0]["series"][0]["points"]), 16)
        self.assertTrue(r["blocks"][0]["text"].startswith("**TTM 3Q26"))   # 최신 분기 TTM
        svg = report_html.CHARTS["line"](rc[0])
        self.assertIn("추정 →", svg)
        self.assertIn('stroke-dasharray="5 4"', svg)
        self.assertIn("(추정)", svg)
