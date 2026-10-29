"""텐배거 리포트 개편 시험 (마스터 지시 2026-10-29 — 수급 볼륨 지표·월주일 피보나치·내러티브 다각 분석·금액 단위 $B·$M·$T)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))

import datapack_check  # noqa: E402
import flow  # noqa: E402
import levels  # noqa: E402
import narrative_view  # noqa: E402
import report_html  # noqa: E402
from units import money_units  # noqa: E402


def bars_from(closes, start="2026-01-05", vol=1000.0):
    from datetime import date, timedelta
    d, out = date.fromisoformat(start), []
    for c in closes:
        while d.weekday() >= 5:
            d += timedelta(days=1)
        out.append({"date": d.isoformat(), "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": vol})
        d += timedelta(days=1)
    return out


class TestUnits(unittest.TestCase):
    def test_money_units(self):
        cases = {"124억$": "$12.4B", "1,472억$": "$147.2B", "250억$": "$25B", "5억$": "$500M", "1.2조$": "$1.2T",
                 "34.2백만 달러": "$34.2M", "100~120억$": "$10~12B", "1조 2,000억$": "$1.2T", "(백만 달러)": "($M)", "매출 M$": "매출 $M"}
        for a, b in cases.items():
            self.assertEqual(money_units(a), b, a)

    def test_money_units_more_forms(self):
        """2026-10-29 보강 — Pulse '506억$' 지적 뒤 남아 있던 형태(만·$앞·억+천만·백만 1,000 이상·불)"""
        cases = {"506억$": "$50.6B", "4,200만$": "$42M", "$3.4억": "$340M", "3억 4천만 달러": "$340M", "3억 4,000만 달러": "$340M",
                 "12,014.9백만$": "$12.0B", "30억 불": "$3B", "30억불": "$3B", "120억~150억$": "$12~15B", "4,000~5,000만$": "$40~50M",
                 "−18억$": "−$1.8B", "10.67억$": "$1.07B", "50만 달러": "$500K", "$1.2조": "$1.2T"}
        for a, b in cases.items():
            self.assertEqual(money_units(a), b, a)

    def test_won_yen_untouched(self):
        for x in ("3,000억 원", "시총 3,700억 엔", "2조 원", "$1.2B", "$3.4억 원", "1만 명", "1억 주", "직원 8만 5천 명"):
            self.assertEqual(money_units(x), x)

    def test_notify_brand_converts(self):
        import notify
        self.assertIn("$12.4B", notify.brand("3Q 124억$ 분할 매도"))


class TestFlow(unittest.TestCase):
    def test_decompose_arithmetic(self):
        bars = bars_from([100.0] * 5, vol=1000.0)
        daily = {b["date"]: {"trf": 400.0, "short": 200.0} for b in bars}
        wk = flow.week_start(bars[0]["date"])
        weekly = {wk: {"ats": 300.0, "otc": 100.0, "retail": 80.0, "firms": {}}}   # 리테일 ÷ 장외 = 0.2
        rows = flow.decompose(bars, daily, weekly)
        self.assertAlmostEqual(rows[0]["off_share"], 0.4)
        self.assertAlmostEqual(rows[0]["retail"], 80.0)    # 400 × 0.2
        self.assertAlmostEqual(rows[0]["inst"], 920.0)
        self.assertAlmostEqual(rows[0]["sr"], 0.5)

    def test_cmf_sign(self):
        rows = [{"h": 10.0, "l": 8.0, "c": 9.9, "inst": 100.0} for _ in range(20)]
        self.assertGreater(flow.cmf(rows)[-1], 0.8)        # 종가가 고가 쪽 = 매집
        rows = [{"h": 10.0, "l": 8.0, "c": 8.1, "inst": 100.0} for _ in range(20)]
        self.assertLess(flow.cmf(rows)[-1], -0.8)

    def test_tags_third_friday_and_earnings(self):
        from datetime import date
        self.assertEqual(flow.third_friday(2026, 9), date(2026, 9, 18))
        tags = flow.tags_for("2026-09-18", "2026-09-17", [], {})
        self.assertIn("분기 만기·지수 정기 변경", tags)
        tags = flow.tags_for("2026-07-31", "2026-07-30", [{"date": "2026-07-30", "tag": "실적 발표", "kind": "earnings"}], {})
        self.assertIn("실적 발표 다음 날", tags)
        self.assertIn("월말", tags)

    def test_pwr_section_offline(self):
        """저장소의 PWR 일봉 + 합성 FINRA(네트워크 없이)로 절이 만들어지는지"""
        bars = flow.load_ohlcv("co-quanta-services")
        self.assertGreater(len(bars), 200)
        daily = {b["date"]: {"trf": b["v"] * 0.4, "short": b["v"] * 0.18} for b in bars[:-1]}
        weekly = {flow.week_start(b["date"]): {"ats": 1.0, "otc": 1.0, "retail": 0.4, "firms": {}} for b in bars}
        sec = flow.report_section("co-quanta-services", {}, finra={"daily": daily, "weekly": weekly}, symbol="PWR")
        self.assertTrue(sec["h2"].startswith("수급 — "))
        self.assertAlmostEqual(sec["_summary"]["retail_share_20"], 0.08, places=3)   # 0.4 × 0.2
        kinds = [b["chart"]["kind"] for b in sec["blocks"] if b["type"] == "chart"]
        self.assertIn("bars", kinds)


class TestLevels(unittest.TestCase):
    def test_fib_values(self):
        ret, ext = levels.fib(408.36, 788.75, True)
        self.assertAlmostEqual(ret["38.2%"], 643.44, places=1)
        self.assertAlmostEqual(ret["50.0%"], 598.56, places=1)
        self.assertAlmostEqual(ret["61.8%"], 553.67, places=1)
        self.assertAlmostEqual(ret["78.6%"], 489.76, places=1)
        ret, _ = levels.fib(527.07, 722.21, False)            # 하락 다리 → 저점에서 위로
        self.assertAlmostEqual(ret["50.0%"], 624.64, places=1)
        self.assertAlmostEqual(ret["61.8%"], 647.67, places=1)
        ret, _ = levels.fib(93.91, 788.75, True)
        self.assertAlmostEqual(ret["23.6%"], 624.77, places=1)
        self.assertAlmostEqual(ret["38.2%"], 523.33, places=1)

    def test_zigzag_pivots(self):
        closes = [100, 104, 110, 120, 112, 100, 95, 101, 108, 115, 124, 118]
        piv = levels.zigzag(bars_from(closes), 0.10)
        kinds = [p[2] for p in piv]
        self.assertEqual(kinds[:3], ["L", "H", "L"])          # 출발 저점 → 120 고점 → 95 저점
        self.assertAlmostEqual(piv[1][1], 120 * 1.01)
        self.assertAlmostEqual(piv[2][1], 95 * 0.99)

    def test_cluster_strength(self):
        lv = [{"price": 600.0, "src": "a", "kind": "fib-주봉", "w": 1.0}, {"price": 602.0, "src": "b", "kind": "fib-일봉", "w": 1.0},
              {"price": 600.0, "src": "c", "kind": "round", "w": 0.5}, {"price": 700.0, "src": "d", "kind": "ma200", "w": 1.0}]
        cl = levels.cluster(lv)
        self.assertEqual(len(cl), 2)
        self.assertAlmostEqual(cl[0]["strength"], 2.5)

    def test_pwr_zones(self):
        """2026-10-29 수기 검증값 — 저항 643~650, 지지 625(200일선·월봉 23.6%·일봉 50%)"""
        daily = flow.load_ohlcv("co-quanta-services")
        z = levels.zones(daily, {"low": {"date": "2022-01-24", "price": 93.91}, "high": {"date": "2026-05-06", "price": 788.75}})
        r0, s0 = z["resistance"][0], z["support"][0]
        self.assertTrue(640 < r0["lo"] < 646 and 645 < r0["hi"] < 652)
        self.assertTrue(620 < s0["mid"] < 630)
        self.assertGreaterEqual(s0["strength"], 3.0)


class TestRender(unittest.TestCase):
    def test_candle_and_stack(self):
        html_c = report_html.chart_candle({"bars": [["2026-10-27", 574.8, 580.9, 566.5, 578.8], ["2026-10-28", 600.0, 609.4, 581.8, 606.9], ["2026-10-29", 632.1, 643.3, 619.6, 610.0]],
                                           "hlines": [{"y": 643.4, "label": "38.2%"}], "zones": [{"y0": 599, "y1": 602, "label": "지지", "tone": "grn"}]})
        self.assertIn("<svg", html_c)
        self.assertEqual(html_c.count('fill="var(--b)"'), 2)   # 상승 2개 빨강(한국식)
        self.assertEqual(html_c.count('fill="var(--c)"'), 1)   # 하락 1개 파랑
        html_s = report_html.chart_bars({"stack": True, "categories": ["a", "b"], "series": [{"name": "기관", "values": [10, 20]}, {"name": "리테일", "color": "b", "values": [1, 2]}]})
        self.assertEqual(html_s.count("<rect"), 4)

    def test_render_applies_units(self):
        d = {"title": "t", "date": "2026-10-29", "ticker": "X", "company": "X", "biz": "b", "summary": [{"q": "q", "a": "매출 124억$"}]}
        self.assertIn("$12.4B", report_html.render(d))


class TestNarrativeAndCheck(unittest.TestCase):
    def test_narrative_section(self):
        dp = {"narrative": {"summary": "s", "stage": "컨센서스", "factors": [{"name": "f", "who": {"sell": "강"}, "drives": "both", "status": "강화"}],
                            "layers": {"retail": {"metrics": [["레딧", "1", "-", "x"]], "read": "r"}}},
              "consensus": {"revisions": {"rows": [{"period": "FY2026", "metric": "EPS", "from": 16.7, "to": 18.1}]}}}
        sec = narrative_view.report_section(dp, {"decomp": {"total": 0.93, "firm": 0.59}})
        self.assertTrue(sec["h2"].startswith("내러티브 — "))
        self.assertIn("+8.4%", sec["blocks"][0]["text"])
        self.assertIsNone(narrative_view.report_section({}))

    def test_check_accepts_newer_balance(self):
        p = {"profile": {"cash": 2.3, "debt": 7.5}, "raw": {"easyconomics_profile": {"total_cash": 0.5, "total_debt": 6.6, "balance_date": "2026-06-30"},
                                                            "balance_2026_09_30": {"cash": 2.3, "debt_current": 0.6, "debt_lt": 6.4, "lease_current": 0.1, "lease_lt": 0.4}}}
        c = next(x for x in datapack_check.check(p)["checks"] if x["name"] == "현금·차입 대조")
        self.assertEqual(c["status"], "통과")
        p["raw"]["easyconomics_profile"]["balance_date"] = "2026-12-31"   # 재무상태표가 더 오래됐으면 예외 없음
        c = next(x for x in datapack_check.check(p)["checks"] if x["name"] == "현금·차입 대조")
        self.assertEqual(c["status"], "실패")


if __name__ == "__main__":
    unittest.main()
