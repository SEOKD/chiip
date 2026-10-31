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

import earnings_view  # noqa: E402
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
        co = {"rev0": 2.0, "unit_usd": 1e9, "market": {"net_debt": 0.3, "shares": 0.1}}
        r = {"mcap": mcap, "unit": "B$", "upside": {"p_h": {2: 0.4, 3: 0.2, 5: 0.05, 10: 0.0}, "required": {2: (0.2, (60.0, 100, "")), 3: (0.3, (90.0, 100, "")), 5: (0.5, (98.0, 100, "")), 10: (0.7, (100.0, 100, ""))}}}
        steps = {str(k): {"path": "p", "outlook": "o", "verdict": "v"} for k in (2, 3, 5, 10)}
        dp = {"ladder": {"exit": {"pe": 20, "net_margin": 0.1, "opm": 0.14}, "base": {"eps": 0.5, "opm": 0.08}, "market": {"name": "M", "size": 100}, "steps": steps}}
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

    def test_required_margin_and_eps(self):
        dp, co, r = self._inputs()
        c = ladder.compute(dp, co, r)
        x = c["rows"][0]
        self.assertAlmostEqual(x["margin"], 0.14)
        self.assertAlmostEqual(x["eps"], 2.0)   # 필요 순이익 0.2 ÷ 주식 0.1
        self.assertAlmostEqual(x["eps_cagr5"], 4 ** 0.2 - 1)
        self.assertEqual((c["eps0"], c["margin0"], c["margin_name"]), (0.5, 0.08, "OPM"))
        sec = ladder.report_section(dp, co, r)
        need = next(b for b in sec["blocks"] if b.get("type") == "table")
        self.assertEqual(need["headers"], ["배수", "목표 시가총액", "필요 매출", "매출 CAGR 5년 / 10년", "OPM", "필요 EPS", "EPS CAGR 5년 / 10년"])
        self.assertEqual(need["rows"][0][:1] + need["rows"][0][4:6], ["**지금**", "8.0%", "$0.50"])
        self.assertEqual(need["rows"][1][4:6], ["14.0%", "$2.00"])
        self.assertTrue(any("**필요 조건:** 매출 $2.00B" in i for b in sec["blocks"] if b.get("type") == "ul" for i in b["items"]))
        self.assertIn("EPS $2.00", ladder.summary_item(dp, co, r)["a"])

    def test_ebitda_exit_and_step_override(self):
        dp, co, r = self._inputs()
        dp["ladder"]["exit"] = {"ev_ebitda": 10, "ebitda_margin": 0.3, "net_margin": 0.1}
        dp["ladder"]["base"] = {"eps": -0.2, "ebitda_margin": 0.2}
        dp["ladder"]["steps"]["10"]["exit"] = {"ebitda_margin": 0.4}
        c = ladder.compute(dp, co, r)
        self.assertAlmostEqual(c["rows"][0]["rev"], (4.0 + 0.3) / 10 / 0.3)
        self.assertAlmostEqual(c["rows"][3]["rev"], (20.0 + 0.3) / 10 / 0.4)
        self.assertEqual(c["margin_name"], "EBITDA Margin")
        self.assertIsNone(c["rows"][0]["eps_cagr5"])   # 기준 EPS 적자면 CAGR을 쓰지 않는다
        self.assertIn("기준 적자", ladder.summary_item(dp, co, r)["a"])
        dp["ladder"]["base"]["cagr_from"] = {"eps": 0.5, "year": 1, "label": "FY2027"}
        c = ladder.compute(dp, co, r)
        self.assertAlmostEqual(c["rows"][0]["eps_cagr5"], (c["rows"][0]["eps"] / 0.5) ** 0.25 - 1)
        sec = ladder.report_section(dp, co, r)
        self.assertIn("−$0.20", sec["blocks"][1]["rows"][0])
        self.assertIn("FY2027 $0.50에서 잰다", sec["blocks"][0]["text"])

    def test_margin_is_required_unless_legacy(self):
        dp, co, r = self._inputs()
        del dp["ladder"]["exit"]["opm"]
        with self.assertRaises(ValueError):
            ladder.report_section(dp, co, r)
        self.assertIn("OPM 미확인", ladder.summary_item(dp, co, r, strict=False)["a"])

    def test_base_eps_from_last_four_quarters(self):
        rows = [{"period": f"2026Q{i}", "metric": "EPS", "actual": 1.0} for i in (1, 2, 3)] + [{"period": "2025Q4", "metric": "EPS", "actual": 2.0}, {"period": "2025Q3", "metric": "EPS", "actual": 9.0}]
        self.assertEqual(ladder.base_eps({"consensus": {"surprise": rows}}), 5.0)
        self.assertIsNone(ladder.base_eps({"consensus": {"surprise": rows[:3]}}))

    def test_section_needs_every_step(self):
        dp, co, r = self._inputs()
        del dp["ladder"]["steps"]["5"]
        with self.assertRaises(ValueError):
            ladder.report_section(dp, co, r)

    def test_monte_carlo_conclusion(self):
        p = {1.5: 0.65, 2: 0.4172, 3: 0.1646, 5: 0.0222, 10: 0.0}
        t = ladder.mc_conclusion(5000, p, [2, 3, 5, 10])
        self.assertEqual(t, "5,000번 돌리면 5년 뒤 주주가치가 지금 시가총액의 2배 이상 2,086번(약 2.4번에 1번) · 3배 이상 823번(약 6.1번에 1번) · 5배 이상 111번(약 45번에 1번) · 10배 이상 0번")
        self.assertNotIn("3배", ladder.mc_conclusion(5000, p, [2]))
        c = {**chart("몬테카를로")["chart"], "conclusion": t, "note": "주석"}
        h = report_html.render({**BASE, "sections": [{"h2": "a", "blocks": [{"type": "chart", "chart": c}]}]})
        self.assertIn(t, h)
        self.assertNotIn("주석", h)
        self.assertIn(t, report_notion.render({**BASE, "sections": [{"h2": "a", "blocks": [{"type": "chart", "chart": c}]}]}))

    def test_monte_carlo_reading(self):
        p = {2: 0.4172, 3: 0.1646, 5: 0.0222, 10: 0.0}
        lines = ladder.mc_reading(5000, 0.56, 0.56, 1.09, 2.13, p, [2, 3, 5, 10])
        self.assertEqual(len(lines), 3)
        self.assertIn("1.00이 지금 주가", lines[0])
        self.assertIn("5,000번 중 2,800번(56%)", lines[1])
        self.assertIn("반반", lines[1])
        self.assertIn("0.56~2.13배", lines[1])
        self.assertIn("2배 이상 2,086번", lines[2])
        self.assertIn("더 많다", ladder.mc_reading(100, 0.7, 1, 1, 1, {}, [2])[1])
        self.assertIn("뒷받침하지 못하는", ladder.mc_reading(100, 0.2, 1, 1, 1, {}, [2])[1])
        c = {**chart("몬테카를로")["chart"], "conclusion": lines}
        doc = {**BASE, "sections": [{"h2": "a", "blocks": [{"type": "chart", "chart": c}, {"type": "chart", "chart": chart("다른 그림")["chart"]}]}]}
        h = report_html.render(doc)
        for line in lines:
            self.assertIn(line.split(":")[0], h)
        self.assertEqual(report_html.under_lines(chart("다른 그림")["chart"]), [])   # 이 그림에만
        self.assertIn(lines[1], report_notion.render(doc))

    def test_large_cap_shows_only_two_times(self):
        dp, co, r = self._inputs(mcap=150.0)
        sec = ladder.report_section(dp, co, r)
        self.assertIn("2배", sec["h2"])
        self.assertNotIn("3", sec["h2"])
        self.assertEqual(ladder.summary_item(dp, co, r)["q"], "2배가 되려면?")


class TestLeadAndMerge(unittest.TestCase):
    def lead(self):
        return {"summary": "s", "value_story": "v", "products": [{"kind": "제품", "name": "n", "what": "w"}],
                "lenses": [{"lens": k, "change": "c", **({"lead_time": {"now": [12, 18], "prior": [18, 24], "prior_when": "2025년", "peers": [{"name": "A", "value": [60, 84]}, {"name": "B", "value": 20}, {"name": "C", "value": "미확인"}]}} if k == "실행 속도" else {})} for k in narrative_view.LENSES],
                "policy": {"fiscal": {"change": "예산 증액", "house": {"level": 5, "why": "세출안 통과"}, "senate": {"level": 2}},
                           "orders": {"change": "해당 없음(관련 명령 없음)"}, "laws": {"change": "법안 발의"}}}

    def test_speed_lens_needs_lead_time(self):
        dp = {"narrative": {"lead": self.lead()}}
        text = json.dumps(narrative_view.lead_section(dp), ensure_ascii=False)
        self.assertIn("납품 리드타임 12~18개월", text)
        self.assertIn("피어 중앙값 46개월보다 67% 짧다(A 60~84개월 · B 20개월 · C 미확인)", text)
        self.assertIn("2025년 18~24개월보다 29% 짧다", text)
        c = narrative_view.speed_compare({"now": 15, "prior": "미확인", "peers": [{"name": "A", "value": "미확인"}]})
        self.assertIsNone(c["vs_prior"])
        self.assertIsNone(c["vs_peer"])
        self.assertIn("이전 대비 미확인", narrative_view.speed_text({"now": 15, "prior": "미확인", "peers": []}))
        speed = next(x for x in dp["narrative"]["lead"]["lenses"] if x["lens"] == "실행 속도")
        del speed["lead_time"]["prior"]
        with self.assertRaises(ValueError):
            narrative_view.lead_section(dp)
        speed["change"] = "해당 없음(납품이 없는 사업)"
        self.assertTrue(narrative_view.lead_section(dp))
        dp["narrative"]["lead"]["lenses"].remove(speed)
        self.assertTrue(narrative_view.lead_section(dp, strict=False))

    def test_policy_three_lines_and_congress_score(self):
        dp = {"narrative": {"lead": self.lead()}}
        ul = next(b for b in narrative_view.lead_section(dp)["blocks"] if b.get("type") == "ul" and any("구조적" in i for i in b["items"]))
        text = " ".join(ul["items"])
        for w in ("재정정책(행정부)", "행정명령(행정부)", "연관입법(의회)"):
            self.assertIn(w, text)
        self.assertIn("의회 동의 7/10", text)
        self.assertIn("하원 5/5(세출안 통과)", text)
        self.assertIn("상원 2/5(한쪽 당 지지만)", text)
        self.assertEqual(text.count("의회 동의"), 1)   # 해당 없음·연관입법에는 붙지 않는다
        dp["narrative"]["lead"]["policy"]["fiscal"].pop("senate")
        with self.assertRaises(ValueError):
            narrative_view.lead_section(dp)
        del dp["narrative"]["lead"]["policy"]
        with self.assertRaises(ValueError):
            narrative_view.lead_section(dp)
        self.assertTrue(narrative_view.lead_section(dp, strict=False))

    def test_lead_needs_six_lenses(self):
        dp = {"narrative": {"lead": self.lead()}}
        sec = narrative_view.lead_section(dp)
        self.assertTrue(sec["h2"].startswith("내러티브 — "))
        self.assertIn("무엇이 기업가치를 바꾸나", [b.get("text") for b in sec["blocks"]])
        dp["narrative"]["lead"]["lenses"].pop()
        with self.assertRaises(ValueError):
            narrative_view.lead_section(dp)

    def test_pipeline_follows_ladder_and_carries_sources(self):
        d = {"sections": [{"h2": "① 실적", "blocks": []}], "summary": [], "sources": ["기존"]}
        pipe = {"h2": "수주·파이프라인 — 진척도와 남은 수익", "blocks": [], "_sources": ["10-Q"]}
        out = v2_to_report.merge_lead(d, {"h2": "내러티브 — 이야기", "blocks": []}, {"h2": "배수 사다리 — 2배", "blocks": []}, [], pipe)
        self.assertEqual([x["h2"][:6] for x in out["sections"]], ["① 내러티브", "② 배수 사", "③ 수주·파", "④ 실적"])
        self.assertEqual(out["sources"], ["기존", "10-Q"])
        self.assertNotIn("_sources", pipe)

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
             "sources": ["기저율: Bessembinder (2018) JFE 129(3) · Greenwood & Hanson (2015) QJE 130(1)", "10-Q 2026-09-25"]}
        h = report_html.render(d)
        for w in ("Greenwood", "Hanson", "Bessembinder", "JFE"):
            self.assertNotIn(w, h)
        self.assertIn("CES 2026", h)
        self.assertIn("10-Q 2026-09-25", h)
        self.assertNotIn("Greenwood", report_notion.render(d))

    def test_citation_outside_parens_fails(self):
        d = {**BASE, "sections": [{"h2": "s", "blocks": [{"type": "p", "text": "Bessembinder 2018은 희귀하다고 했다"}]}]}
        with self.assertRaises(ValueError):
            report_html.render(d)

    def test_vendor_names_leave_no_trace(self):
        text = "Fiscal 자체 추정 $5.85, Zacks CY2027 $6.63, Zacks 의견 7명, Fiscal.ai 일별 배수 기준 EV/매출. Data provided by Zacks Investment Research, Inc., www.zacksdata.com"
        d = {**BASE, "lead": "Fiscal.ai(MCP) 조회", "summary": [{"q": "q", "a": text}],
             "sections": [{"h2": "s", "blocks": [{"type": "p", "text": "**읽는 법:** 지운다"}, {"type": "p", "text": "리비전 출처: Zacks"},
                                                  {"type": "table", "headers": ["a"], "rows": [["Fiscal $3.75B"]], "note": "Zacks 표기"}]}],
             "sources": ["Fiscal.ai MCP 조회", "Zacks 의견", "트랜스크립트는 라이선스 자료", "보강 적용: D-1", "10-K 2025: https://www.sec.gov/x.htm"]}
        for out in (report_html.render(d), report_notion.render(d)):
            for w in ("Fiscal", "Zacks", "zacksdata", "읽는 법", "보강 적용", "MCP", "트랜스크립트"):
                self.assertNotIn(w, out)
        h = report_html.render(d)
        self.assertIn("컨센서스(시장 평균 추정) $5.85", h)
        self.assertIn("컨센서스 CY2027", h)
        self.assertNotIn("모델 추정", h)
        self.assertNotIn("애널리스트 추정", h)
        self.assertIn("애널리스트 의견 7명", h)
        self.assertIn("https://www.sec.gov/x.htm", h)

    def test_saved_json_has_no_vendor_even_in_notes(self):
        d = {**BASE, "sources": ["Zacks 의견", "10-K"], "sections": [{"h2": "s", "blocks": [
            {"type": "chart", "chart": {**chart("주가 vs Fiscal.ai 자체 추정")["chart"], "note": "Data provided by Zacks Investment Research, Inc., www.zacksdata.com"}}]}]}
        out = json.dumps(report_html.clean_vendor(d), ensure_ascii=False)
        for w in ("Fiscal", "Zacks", "zacks"):
            self.assertNotIn(w, out)
        self.assertIn("주가 vs 컨센서스", out)

    def test_unknown_vendor_form_fails(self):
        d = {**BASE, "sections": [{"h2": "s", "blocks": [{"type": "p", "text": "자료는 fiscal.ai 화면"}]}]}
        with self.assertRaises(ValueError):
            report_html.render(d)

    def test_side_notes_are_not_drawn(self):
        d = {**BASE, "verdict": {"view": "v", "upside": 0.2, "upside_basis": "기준 문장"},
             "sections": [{"h2": "s", "blocks": [{"type": "chart", "chart": {**chart("주가")["chart"], "note": "차트 주석"}},
                                                  {"type": "table", "headers": ["a"], "rows": [["1"]], "note": "표 주석"}]}]}
        h = report_html.render(d)
        for w in ("기준 문장", "차트 주석", "표 주석", "업사이드 기준", "↳"):
            self.assertNotIn(w, h)
        self.assertIn("업사이드 +20%", h)

    def test_gloss_once_and_keeps_urls_and_existing(self):
        d = {**BASE, "verdict": {"view": "CAGR이 올랐다. CAGR은 또 올랐다. WFE(장비 투자)와 EV/매출을 본다."},
             "summary": [{"q": "q", "a": "CY2027 추정과 CY2028 추정. SEMI 자료 https://x.com/EPS/WFE"}],
             "sections": [{"h2": "s", "blocks": [{"type": "table", "headers": ["a"], "rows": [["DCF 1.1배"]]}]}]}
        h = report_html.render(d)
        self.assertEqual(h.count("CAGR(연평균 성장률)"), 1)
        self.assertIn("CAGR은 또", h)
        self.assertIn("WFE(장비 투자)", h)
        self.assertIn("EV/매출(기업가치 ÷ 매출)", h)
        self.assertIn("CY2027(캘린더 2027년)", h)
        self.assertIn("CY2028 추정", h)
        self.assertIn("SEMI(국제반도체장비재료협회)", h)
        self.assertIn("https://x.com/EPS/WFE", h)
        self.assertIn("DCF(현금흐름 할인 평가) 1.1배", h)


    def test_no_gloss_terms(self):
        d = {**BASE, "summary": [{"q": "q", "a": "Fwd 1Y P/E와 P/B, EBITDA(상각전영업이익), EPS, 멀티플(배수), EV/EBITDA, EBIT, 멀티플(−54%)"}], "sections": []}
        h = report_html.render(d)
        self.assertIn("Fwd 1Y P/E와 P/B, EBITDA, EPS, 멀티플, EV/EBITDA(기업가치 ÷ 상각전영업이익)", h)
        self.assertIn("EBIT(이자·세금 차감 전 이익)", h)
        self.assertIn("멀티플(−54%)", h)


class TestSurprise(unittest.TestCase):
    ROWS = [{"period": "2026Q2", "metric": "매출", "unit": "M$", "actual": 100, "est": 90, "est_src": "zacks", "basis": "gaap"},
            {"period": "2026Q2", "metric": "EPS", "unit": "$", "actual": 1.2, "est": 1.0, "est_src": "zacks", "basis": "adjusted"},
            {"period": "2026Q2", "metric": "EBIT", "unit": "M$", "actual": 10, "est": 9, "est_src": "zacks", "basis": "adjusted"},
            {"period": "2026Q3", "metric": "매출", "unit": "M$", "actual": 110, "est": 100, "est_src": "fiscal:model", "basis": "gaap"},
            {"period": "2026Q3", "metric": "EPS", "unit": "$", "actual": 1.1, "est": 1.1, "est_src": "fiscal:model", "basis": "adjusted"},
            {"period": "2026Q3", "metric": "EBIT", "unit": "M$", "actual": 11, "est": 9, "est_src": "zacks", "basis": "adjusted"}]

    def _section(self, rows, deltas=None):
        dp = {"id": "x", "consensus": {"surprise": rows}, "call": {"deltas": deltas or []}}
        return earnings_view.report_section(dp, None, 10.0, 0.09, 0.03, "B$")

    def test_chart_has_sales_opm_eps(self):
        sec = self._section(self.ROWS)
        c = next(b["chart"] for b in sec["blocks"] if b["type"] == "chart")
        self.assertEqual([s["name"] for s in c["series"]], ["매출", "OPM", "EPS"])
        self.assertIn("매출·OPM·EPS", c["title"])
        self.assertEqual(c["series"][1]["values"], [None, None, 0.0, None])   # 10% vs 10%, 3분기는 매출·이익 추정 제공처가 달라 비교하지 않는다
        self.assertEqual(c["series"][2]["values"], [None, None, 20.0, 0.0])
        self.assertEqual(len(c["categories"]), 4)
        t = next(b for b in sec["blocks"] if b["type"] == "table")
        self.assertNotIn("추정 출처", t["headers"])

    def test_ebita_margin_replaces_opm(self):
        rows = [{**r, "metric": "EBITA"} if r["metric"] == "EBIT" else r for r in self.ROWS]
        c = next(b["chart"] for b in self._section(rows)["blocks"] if b["type"] == "chart")
        self.assertEqual([s["name"] for s in c["series"]], ["매출", "EBITA Margin", "EPS"])
        self.assertIn("EBITA Margin은 %p", c["title"])

    def test_call_impact_has_no_weighted_figure(self):
        co = {"rev0": 1.0, "s2c": 2.0, "unit_usd": 1e9, "market": {"net_debt": 0.0, "price": 10.0, "shares": 0.1},
              "scenarios": {"base": {"growth": {"start": 0.2, "end": 0.03, "decay": 0.7}, "margin": {"m0": 0.1, "target": 0.1, "lr": 0.1}, "s2c": 2.0}}, "tax": 0.21, "horizon": 10}
        dp = {"id": "x", "consensus": {}, "call": {"deltas": [{"id": "F1", "label": "라벨", "item": "항목", "driver": "growth_start", "shift": 0.01, "confidence": 0.5}]}}
        with mock.patch.object(earnings_view, "call_value_impact", return_value={
                "rows": [{**dp["call"]["deltas"][0], "solo": 0.1, "weighted": 0.05}], "joint": 0.1, "solo_sum": 0.1, "weighted_sum": 0.05, "prior_equity": 1.0, "base_equity": 1.1}):
            sec = earnings_view.report_section(dp, co, 10.0, 0.09, 0.03, "B$")
        self.assertNotIn("확신도 가중", json.dumps(sec, ensure_ascii=False))
        c = next(b["chart"] for b in sec["blocks"] if b["type"] == "chart")
        self.assertEqual(len(c["rows"][0]["bars"]), 1)


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
        self.assertEqual([e["mark"] for e in charts[0]["events"]], ["①", "②"])
        self.assertIn("①", report_html.chart_revision(charts[0]))
        self.assertTrue(report_md.standalone(charts[0]).startswith("<svg"))

    def test_revision_chart_numbers_on_line_and_explains_below(self):
        rev = {"kind": "revision", "title": "EPS 리비전", "unit": "$", "start": "2026-01-01", "end": "2026-10-29",
               "series": [{"name": "CY2027", "color": "b", "points": [["2026-01-01", 2.0], ["2026-03-01", 4.0]]}],
               "events": [{"date": "2026-02-23", "mark": "①", "kind": "실적", "tag": "4Q25 실적", "pct": "+110%"},
                          {"date": "2026-02-26", "mark": "②", "kind": "내러티브", "tag": "전환사채", "pct": "겹침"}]}
        d = {**BASE, "sections": [{"h2": "a", "blocks": [{"type": "chart", "chart": rev}, {"type": "chart", "chart": {**chart("주가")["chart"], "note": "차트 주석"}}]}]}
        h = report_html.render(d)
        self.assertIn("① 26-02-23 4Q25 실적 · EPS 리비전 +110%", h)   # 번호 설명은 그래프 아래
        self.assertIn("② 26-02-26 전환사채 · 실적 창과 겹침", h)
        self.assertNotIn("차트 주석", h)
        svg = report_html.chart_revision(rev)
        self.assertIn(">①<", svg)                                       # 그래프에는 번호만
        self.assertIn(">②<", svg)
        for gone in ("stroke-dasharray", "<circle", "+110%", "전환사채"):
            self.assertNotIn(gone, svg)
        self.assertLess(svg.index(">①<"), svg.index(">②<"))
        self.assertEqual(report_html.under_lines(chart("주가")["chart"]), [])
        for out in (report_notion.render(d), report_notion.render(d, charts=["charts/a.svg", "charts/b.svg"])):
            self.assertIn("- ① 26-02-23 4Q25 실적 · EPS 리비전 +110%", out)

    def test_old_datapack_falls_back(self):
        self.assertEqual(rv.blocks({"id": "x", "consensus": {}}), [])


if __name__ == "__main__":
    unittest.main()
