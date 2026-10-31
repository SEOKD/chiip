"""텐배거 리포트 수주·파이프라인 절 (마스터 지시 2026-10-31)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
import pipeline_view as pv  # noqa: E402


def item(**kw):
    return {"name": "A 프로젝트", "status": "확정", "total": 1.0, "progress": 0.25, "margin": 0.2, "margin_kind": "매출총이익", "margin_basis": "2Q 마진",
            "start": "2026-01", "end": "2027-01", "blockers": ["부품 납기"], "source": "10-Q p.12", **kw}


def dp(*items, **kw):
    return {"unit": "B$", "pipeline": {"as_of": "2026-07-01", "items": list(items), **kw}}


class TestCompute(unittest.TestCase):
    def test_profit_now_and_at_full_progress(self):
        x = pv.compute(dp(item()))["items"][0]
        self.assertAlmostEqual(x["rev_now"], 0.25)
        self.assertAlmostEqual(x["gain_now"], 0.05)
        self.assertAlmostEqual(x["gain_full"], 0.2)

    def test_progress_from_recognized_revenue(self):
        self.assertAlmostEqual(pv.progress_of(item(progress=None, done=0.4)), 0.4)

    def test_speed_against_plan_and_projected_delay(self):
        s = pv.speed_of(item(), "2026-07-01")   # 12개월 중 6개월 지났고 25% → 계획 50%, 18개월 더 걸린다
        self.assertEqual((s["grade"], s["finish"], s["delay"]), ("지연", "2028-01", 12))
        self.assertAlmostEqual(s["gap"], -0.25)
        self.assertEqual(pv.speed_of(item(progress=0.5), "2026-07-01")["grade"], "계획대로")
        self.assertEqual(pv.speed_of(item(progress=0.8), "2026-07-01")["grade"], "앞섬")

    def test_speed_needs_schedule(self):
        self.assertIsNone(pv.speed_of(item(start=None), "2026-07-01"))
        self.assertEqual(pv.speed_text({**item(), "speed_calc": None, "speed": "분기 45MW"}), "분기 45MW")
        self.assertEqual(pv.speed_text({**item(), "speed_calc": None}), "미확인")


class TestSection(unittest.TestCase):
    def rows(self, sec, title):
        return next(b for b in sec["blocks"] if b.get("title") == title)["rows"]

    def test_lists_every_required_field(self):
        sec = pv.report_section(dp(item()), {"mcap": 1.0})
        row = self.rows(sec, "수주·파이프라인 진척")[0]
        self.assertEqual(row[:3], ["A 프로젝트", "확정", "25%"])
        self.assertIn("지연", row[3])
        self.assertIn("부품 납기", row[4])
        self.assertEqual(self.rows(sec, "진척도별 수익")[0], ["A 프로젝트", "매출총이익 20%", "$0.25B", "$0.05B", "$1.00B", "$0.20B"])
        self.assertTrue(any("시가총액의 15%" in str(b.get("text")) for b in sec["blocks"]))

    def test_unconfirmed_stays_out_of_firm_total(self):
        sec = pv.report_section(dp(item(), item(name="MOU 건", status="MOU", total=5.0)))
        rows = self.rows(sec, "합계")
        self.assertEqual(rows[0][1], "$1.00B")
        self.assertEqual(rows[1][:2], ["**미확정 합계**", "$5.00B"])

    def test_unknown_is_shown_not_filled(self):
        sec = pv.report_section(dp(item(progress="미확인", margin="미확인")))
        self.assertEqual(self.rows(sec, "수주·파이프라인 진척")[0][2], "미확인")
        self.assertEqual(self.rows(sec, "진척도별 수익")[0][2:6], ["미확인", "미확인", "$1.00B", "미확인"])
        self.assertEqual(self.rows(sec, "합계")[0][4], "미확인")
        self.assertFalse(any("남는 이익" in str(b.get("text")) for b in sec["blocks"]))

    def test_partial_unknown_is_marked_in_total(self):
        sec = pv.report_section(dp(item(), item(name="B", progress="미확인")))
        self.assertIn("미확인 1건", self.rows(sec, "합계")[0][2])

    def test_company_without_orders_has_no_section(self):
        self.assertIsNone(pv.report_section({"pipeline": {"none": "구독 소프트웨어"}}))

    def test_strict_needs_pipeline_but_legacy_does_not(self):
        with self.assertRaises(ValueError):
            pv.report_section({})
        self.assertIsNone(pv.report_section({}, strict=False))

    def test_rejects_invented_or_incomplete_rows(self):
        for bad in (item(status="수주"), item(source=None), item(blockers=[]), item(progress=None), item(progress=1.2), item(margin=None), item(margin_basis=None)):
            with self.assertRaises(ValueError):
                pv.report_section(dp(bad))


if __name__ == "__main__":
    unittest.main()
