"""텐배거 일일 리포트 렌더러·선정기 시험 — 2026-10-29"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))

import pick_report  # noqa: E402
import report_html  # noqa: E402


class TestRender(unittest.TestCase):
    def base(self):
        return {"title": "T", "date": "2026-10-29", "ticker": "X", "company": "Co", "biz": "사업",
                "verdict": {"view": "판단 **굵게**", "confidence": "중", "insight": 7},
                "sections": [{"h2": "차트", "blocks": [
                    {"type": "chart", "chart": {"kind": "line", "title": "L", "series": [{"name": "s", "points": [["2026-01", 1], ["2026-02", 3]]}]}},
                    {"type": "chart", "chart": {"kind": "bars", "title": "B", "categories": ["a", "b"], "series": [{"name": "s", "values": [1, None]}]}},
                    {"type": "chart", "chart": {"kind": "hbars", "title": "H", "rows": [{"label": "r", "bars": [{"name": "x", "value": 2}]}]}},
                    {"type": "chart", "chart": {"kind": "scenario", "title": "S", "current": 100, "cases": [
                        {"name": "약세", "value": 50, "prob": 0.5}, {"name": "강세", "value": 300, "prob": 0.5}]}}]}]}

    def test_render_all_charts_and_escape(self):
        d = self.base()
        d["summary"] = [{"q": "<script>alert(1)</script>", "a": "ok"}]
        h = report_html.render(d)
        self.assertEqual(h.count("<svg"), 4)
        self.assertNotIn("<script>alert", h)                 # 수집 문장 속 스크립트는 이스케이프
        self.assertIn("<b>굵게</b>", h)
        self.assertIn("확률 가중 175", h)                     # 0.5×50 + 0.5×300
        self.assertIn("투자 권유가 아님", h)
        self.assertNotIn("NaN", h)

    def test_brand_chiip(self):
        """텔레그램·GitHub 보고는 '치입' 대신 'Chiip'(마스터 지시 2026-10-29)"""
        d = self.base()
        d["verdict"]["view"] = "치입 판단: 조건부"
        h = report_html.render(d)
        self.assertNotIn("치입", h)
        self.assertIn("Chiip View", h)
        sys.path.insert(0, str(ROOT / "radar"))
        import notify
        self.assertEqual(notify.brand("[치입 펄스 16:04] 치입은"), "[Chiip Pulse 16:04] Chiip은")

    def test_required_fields(self):
        d = self.base()
        del d["biz"]
        with self.assertRaises(ValueError):
            report_html.render(d)


class TestPick(unittest.TestCase):
    def test_queue_first_then_skip_recent(self):
        with tempfile.TemporaryDirectory() as tmp:
            q, log = Path(tmp) / "q.txt", Path(tmp) / "log.csv"
            q.write_text("CBRS\n", encoding="utf-8")
            with mock.patch.object(pick_report, "QUEUE", q), mock.patch.object(pick_report, "LOG", log):
                p = pick_report.pick(date(2026, 10, 29))
                self.assertEqual(p["reason"], "마스터 요청 대기열")
                pick_report.done(p["id"], "CBRS", "x.html", "v", date(2026, 10, 29))
                self.assertEqual(q.read_text(encoding="utf-8"), "")
                self.assertNotEqual(pick_report.pick(date(2026, 10, 30)).get("ticker"), "CBRS")   # 30일 안 재작성 금지


if __name__ == "__main__":
    unittest.main()


sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
import build_drivers  # noqa: E402
import v2_to_report  # noqa: E402


class TestDatapackToDrivers(unittest.TestCase):
    def pack(self, **kw):
        p = {"id": "x", "name": "X", "industry": "semiconductor", "region_mix": {"US": 1.0},
             "profile": {"price": 10, "shares_basic": 1.0, "cash": 2, "debt": 1},
             "dilution": {"warrants": 0.1}, "financials": {"rev_ttm": 1.0, "ebit_ttm": 0.1, "invested_capital": 0.5},
             "consensus": {"rev": {"FY2026": 1.2, "FY2027": 1.5, "FY2028": 1.8}, "ebit_margin": {"FY2026": 0.10, "FY2027": 0.15}},
             "call": {"tone": "down", "risks": ["고객 집중"]}}
        p.update(kw)
        return p

    def test_consensus_and_call_become_drivers(self):
        d = build_drivers.build(self.pack())
        self.assertAlmostEqual(d["rev0"], 1.2)
        self.assertAlmostEqual(d["scenarios"]["base"]["growth"]["start"], 0.25, places=3)   # 1.5/1.2−1
        self.assertEqual(d["scenarios"]["bear"]["prob"], 0.30)                              # 콜 톤 down → 약세 확률↑
        self.assertAlmostEqual(d["market"]["shares"], 1.1)                                  # 워런트 포함 완전 희석
        self.assertAlmostEqual(d["market"]["net_debt"], -1.0)
        self.assertIn("컨센서스", d["provenance"]["growth"])

    def test_guidance_overrides_consensus_and_guardrails(self):
        d = build_drivers.build(self.pack(guidance={"rev_fy0": [1.3, 1.5]}))
        self.assertAlmostEqual(d["rev0"], 1.4)
        hyper = build_drivers.build(self.pack(consensus={"rev": {"FY2026": 1.0, "FY2027": 3.3}}))
        self.assertLessEqual(hyper["mc"]["sigma_growth"], 0.12)                              # 초고성장 변동성 상한
        self.assertEqual(hyper["scenarios"]["base"]["growth"]["decay"], 0.45)

    def test_comps_and_histogram(self):
        cp = v2_to_report.comps([{"growth_ntm": g, "ev_sales_ntm": 2 + 10 * g} for g in (0.1, 0.2, 0.3, 0.4)], 0.5, 9.0)
        self.assertAlmostEqual(cp["implied"], 7.0, places=3)
        self.assertAlmostEqual(cp["r2"], 1.0, places=6)
        labels, pct = v2_to_report.histogram([i / 100 for i in range(100)], bins=5, lo=0, hi=1)
        self.assertEqual(len(labels), 5)
        self.assertAlmostEqual(sum(pct), 100, places=0)


sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
import datapack_check  # noqa: E402
import dcf  # noqa: E402
import scenarios  # noqa: E402


class TestValuationAudit(unittest.TestCase):
    """2026-10-29 CBRS 전 과정 점검에서 나온 결함의 회귀 시험"""

    def test_cbrs_datapack_matches_raw(self):
        r = datapack_check.check(datapack_check.load("us-cbrs"))
        self.assertEqual([c for c in r["checks"] if c["status"] != "통과" and not c["name"].startswith("기준 멀티플")], [])   # 옛 묶음은 Fwd 1Y 재료만 경고

    def test_checker_catches_old_errors(self):
        p = datapack_check.load("us-cbrs")
        p["financials"]["ebit_ttm"] = -0.9          # 1H 연환산 근사
        p["call"]["tone"] = "flat"                   # 레이더는 상향
        p["peers"] = p["peers"][:2]
        bad = {c["name"] for c in datapack_check.check(p)["checks"] if c["status"] == "실패"}
        self.assertTrue({"TTM 영업이익 = 4분기 합", "어닝콜 톤 = 실적 레이더", "동종사 4곳 이상·기준 표기"} <= bad)

    def test_margin_anchor_keeps_consensus_year1(self):
        path = scenarios.margin_spec_path({"m0": -0.55, "target": 0.22, "year_target": 4, "lr": 0.15, "lam": 0.35, "anchors": [0.03]}, 10)
        self.assertAlmostEqual(path[0], 0.03)        # 덮어쓰기와 무관하게 1년차 = 컨센서스
        self.assertAlmostEqual(path[3], 0.22)

    def test_non_gaap_margin_subtracts_sbc_and_tone_from_radar(self):
        p = TestDatapackToDrivers().pack(consensus={"rev": {"FY2026": 1.0, "FY2027": 1.5}, "ebit_margin": {"FY2026": 0.0, "FY2027": 0.10},
                                                    "margin_basis": "non_gaap"}, sbc_pct_rev=0.05, call={"guidance_direction": "raise"})
        d = build_drivers.build(p)
        self.assertAlmostEqual(d["scenarios"]["base"]["margin"]["anchors"][0], 0.05)
        self.assertEqual(d["scenarios"]["bull"]["prob"], 0.30)   # 가이던스 상향 → up

    def test_future_equity_grows_near_cost_of_capital(self):
        d = {"rev0": 1.0, "growth": [1.0, 0.5, 0.3, 0.2, 0.1, 0.05, 0.04, 0.04, 0.04, 0.04], "margin": [0.2] * 10, "tax": 0.21, "s2c": 1.0,
             "ic0": 1.0, "wacc": 0.10, "g_term": 0.03, "net_debt": 0.0, "shares": 1.0, "kd": 0.04}
        e0, e5 = dcf.value(d)["equity"], dcf.equity_at(d, 5)
        self.assertLess((e5 / e0) ** 0.2 - 1, 0.13)   # 적자 재투자를 싼 차입으로 메워 부풀리지 않는다


import multiples  # noqa: E402


class TestMultiples(unittest.TestCase):
    """멀티플 엔진(2026-10-29 마스터 지시 — 동종 레인지·할인 분해·ROIC 비례 멀티플)"""

    def test_value_driver_formula(self):
        row = next(r for r in multiples.steady_state_table(0.10, 0.03) if r["roic"] == 0.15)
        self.assertAlmostEqual(row["ev_nopat"], (1 - 0.03 / 0.15) / (0.10 - 0.03))
        self.assertAlmostEqual(row["ev_sales"][0.22], row["ev_nopat"] * 0.22 * 0.79)

    def test_goodwill_excluded_for_reinvestment(self):
        p = {"rev": 10.0, "ebit_margin": 0.2, "mcap": 100.0, "pb": 5.0, "debt": 2.0, "cash": 2.0, "goodwill": 12.0, "intangibles": 3.0}
        roic, roic_ex, s2c, ic = multiples.peer_fundamentals(p)
        self.assertAlmostEqual(roic, 10 * 0.2 * 0.79 / 20)       # 영업권 포함 투하자본 20
        self.assertAlmostEqual(roic_ex, 10 * 0.2 * 0.79 / 5)     # 영업권·무형 제외 5
        self.assertAlmostEqual(s2c, 2.0)

    def _forward_dp(self, **kw):
        peers = [{"ticker": t, "rev": 2.0, "ebit_margin": 0.15, "mcap": 8.0, "pb": 4.0, "debt": 1.0, "cash": 0.5, "ev_sales": 4.0, "growth": 0.15, "pe_fwd": pe, "ev_ebitda_fwd": ee}
                 for t, pe, ee in (("A", 15.0, 10.0), ("B", 20.0, 12.0), ("C", 25.0, 14.0), ("D", 30.0, 16.0))]
        return {"profile": {"debt": 1.0, "cash": 2.0}, "financials": {"rev_ttm": 5.0}, "peers": peers, "history": {"pe_fwd": [{"date": "2026-01-30", "value": 22.0}], "ev_ebitda_fwd": [{"date": "2026-01-30", "value": 11.0}]},
                "multiples_now": {"pe_fwd": 12.0, "ev_ebitda_fwd": 8.0, "ev_sales": 1.8}, **kw}

    def test_three_horizons_each_get_a_chart(self):
        base = {"rev0": 5.0, "growth": [0.2] * 5, "margin": [0.2] * 5, "tax": 0.21, "s2c": 2.0, "ic0": 3.0, "wacc": 0.1, "g_term": 0.03, "net_debt": -1.0, "shares": 1.0}
        dp = self._forward_dp(main_metric="eps", forward={"horizons": {"2": {"ext": 0}, "3": {"ext": 2}}})
        dp["multiples_now"].update({"pe_fwd2": 9.0, "pe_fwd3": 7.5})
        for i, p in enumerate(dp["peers"]):
            p.update({"pe_fwd2": 12.0 + i, "pe_fwd3": 10.0 + i})
        m = multiples.analyze(dp, base, 12.0, 0.1, 0.03)
        self.assertEqual([v["label"] for v in m["horizons"]], ["Fwd 1Y P/E", "Fwd 2Y P/E", "Fwd 3Y P/E"])
        self.assertAlmostEqual(m["horizons"][2]["target_warranted"], m["target_warranted"] * 7.5 / 12.0)   # 시장÷내재는 세 분류 공통
        self.assertEqual(m["horizons"][1]["history"], None)
        self.assertEqual(m["ext"], 2)
        bl = multiples.report_blocks(m, "B$", 12.0, "대상")
        titles = [b["chart"]["title"] for b in bl if b["type"] == "chart"]
        self.assertEqual(titles, [f"Fwd {h}Y P/E — 과거·동종·펀더멘털·합리적 멀티플 (배)" for h in (1, 2, 3)])
        table = next(b for b in bl if b["type"] == "table")
        self.assertEqual(table["headers"][1:4], ["Fwd 1Y P/E", "Fwd 2Y P/E", "Fwd 3Y P/E"])
        self.assertEqual(len({len(r) for r in table["rows"]} | {len(table["headers"])}), 1)
        self.assertIn("최대 2개 분기를 마지막 회계연도 추정 성장률로 연장", json.dumps(bl, ensure_ascii=False))
        for row in dp["peers"][:2]:      # 동종이 모자란 분류는 그리지 않는다
            row.pop("pe_fwd3")
        self.assertEqual([v["h"] for v in multiples.analyze(dp, base, 12.0, 0.1, 0.03)["horizons"]], [1, 2])

    def test_main_metric_picks_multiple(self):
        dp = self._forward_dp(forward={"ntm": {"eps": 5.0, "ebitda": 1.0, "ebit": 0.8}, "guided": {"eps": True}})
        self.assertEqual(multiples.choose_basis(dp)[0], "pe_fwd")
        heavy = self._forward_dp(forward={"ntm": {"eps": 1.0, "ebitda": 1.0, "ebit": 0.4}})          # 감가상각 60%
        self.assertEqual(multiples.choose_basis(heavy)[0], "ev_ebitda_fwd")
        loss = self._forward_dp(forward={"ntm": {"eps": -1.0, "ebitda": 1.0, "ebit": 0.9}})
        self.assertEqual(multiples.choose_basis(loss)[0], "ev_ebitda_fwd")
        guided = self._forward_dp(forward={"ntm": {"eps": 1.0, "ebitda": 1.0, "ebit": 0.9}, "guided": {"ebitda": True}})
        self.assertEqual(multiples.choose_basis(guided)[0], "ev_ebitda_fwd")
        self.assertEqual(multiples.choose_basis(self._forward_dp(main_metric="ebitda"))[0], "ev_ebitda_fwd")   # 묶음에 적으면 그대로
        no_peers = self._forward_dp()
        no_peers["peers"] = no_peers["peers"][:2]
        self.assertEqual(multiples.choose_basis(no_peers)[0], "ev_sales")                                       # 재료가 없을 때만

    def test_forward_pe_analysis_keeps_value_identity(self):
        base = {"rev0": 5.0, "growth": [0.2] * 5, "margin": [0.2] * 5, "tax": 0.21, "s2c": 2.0, "ic0": 3.0, "wacc": 0.1, "g_term": 0.03, "net_debt": -1.0, "shares": 1.0}
        for main, key, lb in (("eps", "pe_fwd", "Fwd 1Y P/E"), ("ebitda", "ev_ebitda_fwd", "Fwd 1Y EV/EBITDA")):
            dp = self._forward_dp(main_metric=main)
            m = multiples.analyze(dp, base, 12.0, 0.1, 0.03)
            self.assertEqual((m["basis"], m["label"], m["current"]), (key, lb, dp["multiples_now"][key]))
            self.assertEqual(m["history"]["p50"], dp["history"][key][0]["value"])
            # 시장÷내재는 EV끼리 — 어느 배수로 보든 같다
            ev = multiples.dcf.value(base)["ev"]
            self.assertAlmostEqual(m["current"] / m["target_warranted"], 11.0 / ev)
            self.assertAlmostEqual(m["rational_value_x"]["p50"], (ev * m["sentiment"]["p50"] + 1.0) / 12.0)
            self.assertAlmostEqual(m["decomp"]["fundamental"] + m["decomp"]["firm"], m["decomp"]["total"])
            bl = multiples.report_blocks(m, "B$", 12.0, "대상")
            text = json.dumps(bl, ensure_ascii=False)
            self.assertIn(f"기준 멀티플은 {lb}", text)
            self.assertIn(f"{lb} — 과거·동종·펀더멘털·합리적 멀티플", text)
            self.assertNotIn("EV/매출", text)

    def test_levered_peer_uses_ev_ratio_and_forward_margin(self):
        base = {"rev0": 5.0, "growth": [0.2] * 5, "margin": [0.2] * 5, "tax": 0.21, "s2c": 2.0, "ic0": 3.0, "wacc": 0.1, "g_term": 0.03, "net_debt": -1.0, "shares": 1.0}
        dp = self._forward_dp(main_metric="eps")
        dp["peers"][0].update({"debt": 6.0, "ntm_ebit_margin": 0.3, "ntm_growth": 0.25})   # 차입이 커도 주주가치 잔액으로 폭주하지 않는다
        m = multiples.analyze(dp, base, 12.0, 0.1, 0.03)
        a = next(x for x in m["peers"] if x["ticker"] == "A")
        self.assertEqual((a["ebit_margin"], a["growth"]), (0.3, 0.25))
        w = multiples.warranted_ev_sales(2.0, 0.25, 0.3, a["s2c"], multiples.peer_fundamentals(a)[3], 0.1, 0.03) * 2.0
        self.assertAlmostEqual(a["ratio"], (8.0 + 5.5) / w)
        self.assertAlmostEqual(a["warranted"], 15.0 / a["ratio"])

    def test_cbrs_decomposition_is_exact(self):
        import run as v2run
        co = v2run.load_company("us-cbrs")
        co["market"] = v2run.resolve_market(co)
        r = v2run.evaluate("us-cbrs", draws=50)
        base = scenarios.drivers(co, co["scenarios"]["base"], r["coc"]["wacc"], r["g_term"])
        m = multiples.analyze(datapack_check.load("us-cbrs"), base, r["mcap"], r["coc"]["wacc"], r["g_term"])
        d = m["decomp"]
        self.assertAlmostEqual(d["fundamental"] + d["firm"], d["total"])   # 두 몫의 곱 = 전체
        self.assertTrue(all(x["warranted"] is None or x["warranted"] > 0 for x in m["peers"]))   # 음수 내재 멀티플은 버린다
        self.assertGreater(m["history"]["p50"], m["current"])              # 상장 이후 멀티플이 식었다


import earnings_view  # noqa: E402


class TestEarningsView(unittest.TestCase):
    """어닝콜 변화 가치 영향·서프라이즈·리비전·멀티플 프리미엄(2026-10-29 마스터 지시)"""

    def co(self):
        return {"rev0": 1.0, "ic0": 0.5, "tax": 0.21, "horizon": 10, "market": {"net_debt": 0.0, "shares": 1.0},
                "scenarios": {"base": {"growth": {"start": 0.20, "end": 0.03, "decay": 0.7},
                                       "margin": {"m0": 0.15, "target": 0.20, "year_target": 3, "lr": 0.18, "lam": 0.3}, "s2c": 2.0}}}

    def test_call_delta_reverts_driver(self):
        imp = earnings_view.call_value_impact(self.co(), 0.09, 0.03, [
            {"id": "F1", "driver": "margin_target", "shift": 0.02, "confidence": 0.8},
            {"id": "F2", "driver": "wacc", "shift": 0.01, "confidence": 0.5},
            {"id": "F3", "kind": "반복", "driver": None, "shift": 0}])
        f1, f2, f3 = imp["rows"]
        self.assertGreater(f1["solo"], 0)                 # 목표 이익률이 올랐다 → 가치 +
        self.assertLess(f2["solo"], 0)                    # 할인율이 올랐다 → 가치 −
        self.assertEqual(f3["solo"], 0.0)                 # 반복은 0
        self.assertAlmostEqual(f1["weighted"], f1["solo"] * 0.8)
        co = self.co()
        co["scenarios"]["base"]["margin"]["target"] -= 0.02
        prior = earnings_view._equity(co, co["scenarios"]["base"], 0.09, 0.03)
        self.assertAlmostEqual(f1["solo"], imp["base_equity"] / prior - 1)

    def test_revisions_and_price_decomposition(self):
        r = earnings_view.revisions({"rows": [{"period": "Q4", "metric": "EPS", "from": 0.18, "to": 0.1768},
                                              {"period": "Q1", "metric": "EPS", "from": 0.16, "to": 0.1671}]},
                                    {"from": 26.22, "to": 18.35})
        self.assertAlmostEqual(r["total"]["EPS"]["rev"], (0.1768 + 0.1671) / 0.34 - 1)
        d = r["decomp"]
        self.assertAlmostEqual((1 + d["eps"]) * (1 + d["rerate"]), 1 + d["price"])   # 곱 분해가 정확

    def test_premiums_use_forward_earnings_first(self):
        peers = [{"pe_fwd": 15, "ev_ebitda_fwd": 10, "ev_sales": 3}, {"pe_fwd": 25, "ev_ebitda_fwd": 14, "ev_sales": 5}]
        pm = earnings_view.premiums({"pe_fwd": 20, "ev_ebitda_fwd": 12, "ev_sales": 4}, peers)
        self.assertEqual([x["metric"] for x in pm], ["Fwd 1Y P/E", "Fwd 1Y EV/EBITDA"])
        p2 = earnings_view.premiums({"pe_fwd": 20, "pe_fwd2": 15}, [{"pe_fwd": 15, "pe_fwd2": 10}, {"pe_fwd": 25, "pe_fwd2": 14}])
        self.assertEqual([x["metric"] for x in p2], ["Fwd 1Y P/E", "Fwd 2Y P/E"])
        self.assertEqual([x["metric"] for x in earnings_view.premiums({"ev_sales": 4}, peers)], ["EV/매출"])   # 선행 재료가 없을 때만

    def test_premiums_and_surprise(self):
        pm = earnings_view.premiums({"pe_fwd": 30, "growth": 0.30},
                                    [{"pe_fwd": 20, "growth": 0.10}, {"pe_fwd": 15, "growth": 0.05}, {"pe_fwd": 25, "growth": 0.20}])
        self.assertAlmostEqual(pm[0]["premium"], 30 / 20 - 1)
        self.assertLess(pm[0]["growth_adj_premium"], 0)   # 성장이 높아 성장 조정하면 할인
        sp = earnings_view.surprises([{"actual": 1167.9, "est": 1045.7}])
        self.assertAlmostEqual(sp[0]["surprise"], 1167.9 / 1045.7 - 1)

    def test_surprise_keeps_last_four_quarters(self):
        rows = [{"period": f"2025Q{q}", "metric": "매출", "actual": 10 + q, "est": 10} for q in (1, 2, 3, 4)] +                [{"period": "2026Q1", "metric": "매출", "actual": 15, "est": 12}, {"period": "2026Q1", "metric": "EPS", "actual": 1.1, "est": 1.0}]
        sp = earnings_view.surprises(rows)
        self.assertEqual(sorted({r["period"] for r in sp}), ["2025Q2", "2025Q3", "2025Q4", "2026Q1"])   # 마스터 지시 2026-10-30 — 최근 4개 분기

    def test_call_chart_uses_item_names_not_ids(self):
        dp = {"call": {"prev_date": "2026-08-01", "date": "2026-10-29", "deltas": [
            {"id": "F1", "kind": "신규", "item": "OpenAI 2GW 옵션 행사 가능성 언급", "label": "OpenAI 2GW 옵션", "driver": "growth_start", "shift": 0.05, "confidence": 0.5},
            {"id": "F2", "kind": "업데이트", "item": "장기 코어 영업이익률 목표 하향 조정", "driver": "margin_target", "shift": -0.02, "confidence": 0.8}]}}
        sec = earnings_view.report_section(dp, self.co(), 10.0, 0.09, 0.03, "B$")
        ch = [b["chart"] for b in sec["blocks"] if b.get("type") == "chart" and b["chart"]["title"].startswith("콜 변화")][0]
        labels = [r["label"] for r in ch["rows"]]
        self.assertEqual(ch["kind"], "hbars")
        self.assertIn("OpenAI 2GW 옵션", labels)
        self.assertTrue(any(l.startswith("장기 코어 영업이익률") for l in labels))
        self.assertFalse(any(l in ("F1", "F2") for l in labels))
        html = report_html.chart_hbars(ch)   # 음수 막대도 그린다
        self.assertIn("stroke-dasharray", html)
