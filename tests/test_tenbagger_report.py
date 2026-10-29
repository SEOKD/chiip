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
        self.assertIn("Chiip 판단", h)
        sys.path.insert(0, str(ROOT / "radar"))
        import notify
        self.assertEqual(notify.brand("[치입 펄스 16:04] 치입은"), "[Chiip 펄스 16:04] Chiip은")

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
        self.assertEqual(r["score"], 10.0, [c for c in r["checks"] if c["status"] != "통과"])

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
