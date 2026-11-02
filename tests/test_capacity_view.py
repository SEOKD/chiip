"""리포트 생산능력 절 (마스터 지시 2026-11-02)"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import capacity_view as cv  # noqa: E402

CAP = {"as_of": "2026-09-30", "unit": "MW/년", "summary": "증설이 병목이다.", "sites_none": "임차 시설뿐이다",
       "current": {"nameplate": 1000, "utilization": 0.8, "basis": "공시", "source": "10-K"},
       "plans": [{"name": "A 공장", "add": 500, "stage": "착공", "online": "2027-06", "capex": 1.0, "blocker": "변압기", "source": "s1"},
                 {"name": "B 공장", "add": 300, "stage": "발표", "online": "미확인", "capex": "미확인", "blocker": "인허가", "source": "s2"},
                 {"name": "C 공장", "add": 100, "stage": "가동", "online": "2026-03", "capex": 0.2, "blocker": "없음", "source": "s3"}],
       "capex": [{"period": "FY25", "capex": 0.5, "rev": 5.0, "kind": "실적"}, {"period": "FY26", "capex": 0.9, "rev": 6.0, "kind": "가이던스"}]}
DP = {"unit": "B$", "capacity": CAP}


class TestCompute(unittest.TestCase):
    def test_nameplate_is_not_sellable(self):
        self.assertEqual(cv.compute(DP)["real"], 800)

    def test_announcement_is_not_firm_and_live_is_excluded(self):
        c = cv.compute(DP)
        self.assertEqual((c["add_firm"], c["add_all"]), (500, 800))
        self.assertEqual(c["capex_all"], 1.0)
        self.assertEqual(c["unpriced"], 1)

    def test_capex_share_of_revenue(self):
        self.assertAlmostEqual(cv.compute(DP)["years"][1]["pct"], 0.15)

    def test_unit_capex_uses_priced_plans_only(self):
        self.assertAlmostEqual(cv.compute(DP)["per_unit"], 0.002)


class TestGate(unittest.TestCase):
    def bad(self, change):
        c = copy.deepcopy(CAP)
        change(c)
        with self.assertRaises(ValueError):
            cv.check(c)

    def test_good(self):
        cv.check(CAP)

    def test_stage_must_be_known(self):
        self.bad(lambda c: c["plans"][0].update(stage="검토"))

    def test_blank_is_not_unknown(self):
        self.bad(lambda c: c["plans"][0].pop("capex"))
        self.bad(lambda c: c["current"].pop("utilization"))

    def test_capex_needs_two_periods(self):
        self.bad(lambda c: c["capex"].pop())

    def test_missing_material_stops(self):
        with self.assertRaises(SystemExit):
            cv.section({})

    def test_none_skips(self):
        dp = {"capacity": {"none": "소프트웨어"}}
        self.assertIsNone(cv.section(dp))
        self.assertEqual(cv.charts(dp), (None, None))
        self.assertIsNone(cv.summary_item(dp))


class TestReport(unittest.TestCase):
    def test_section(self):
        sec = cv.section(DP)
        text = str(sec["blocks"])
        self.assertEqual(sec["h2"], "생산능력")
        self.assertIn("FY25 CAPEX", text)
        self.assertIn("매출의 10.0%", text)
        self.assertIn("금액 미확인 1건 제외", text)
        for b in sec["blocks"]:
            if b.get("type") == "table":
                self.assertLessEqual(len(b["headers"]), 5)

    def test_unknown_capacity_stays_unknown(self):
        cap = copy.deepcopy(CAP)
        cap["current"]["nameplate"] = "미확인"
        dp = {"unit": "B$", "capacity": cap}
        self.assertIn("미확인", cv.section(dp)["blocks"][0]["text"])
        self.assertIsNone(cv.charts(dp)[0])

    def test_charts(self):
        ladder, years = cv.charts(DP)
        self.assertEqual([r["label"] for r in ladder["rows"]], ["가동률 반영 현재", "명목 현재", "착공 이상 반영", "발표까지 반영"])
        self.assertEqual(ladder["rows"][-1]["bars"][0]["value"], 1800)
        self.assertEqual(years["rows"][1]["bars"][0]["value"], 15.0)


if __name__ == "__main__":
    unittest.main()
