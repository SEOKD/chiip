"""리포트 고객 절 (마스터 지시 2026-11-02)"""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import customer_view as cv  # noqa: E402

CU = {"as_of": "2026-09-30", "period": "FY25", "summary": "두 곳이 절반이다.",
      "items": [{"name": "Lam Research", "share": 0.3, "prior": 0.25, "basis": "공시", "buys": "가스 패널", "source": "10-K"},
                {"name": "Applied Materials", "alias": "Customer B", "share": [0.2, 0.3], "prior": "미확인", "basis": "추정", "buys": "모듈", "source": "콜", "why": "제품 구성"},
                {"name": "ASML", "share": "미확인", "prior": "미확인", "basis": "보도", "buys": "프레임", "source": "기사", "why": "보도"}]}
DP = {"customers": CU}


class TestCompute(unittest.TestCase):
    def test_mix(self):
        c = cv.compute(DP)
        self.assertAlmostEqual(c["top3"], 0.55)
        self.assertAlmostEqual(c["rest"], 0.45)
        self.assertAlmostEqual(c["hhi"], 0.1525)
        self.assertEqual(c["grade"], "보통")

    def test_only_disclosed_counts_as_confirmed(self):
        self.assertAlmostEqual(cv.compute(DP)["firm"], 0.3)


class TestGate(unittest.TestCase):
    def bad(self, change):
        c = copy.deepcopy(CU)
        change(c)
        with self.assertRaises(ValueError):
            cv.check(c)

    def test_good(self):
        cv.check(CU)

    def test_estimate_needs_reason(self):
        self.bad(lambda c: c["items"][1].pop("why"))

    def test_mix_cannot_exceed_whole(self):
        self.bad(lambda c: c["items"][0].update(share=0.9))

    def test_needs_one_share(self):
        self.bad(lambda c: [x.update(share="미확인") for x in c["items"]])

    def test_missing_material_stops(self):
        with self.assertRaises(SystemExit):
            cv.section({})

    def test_none_skips(self):
        dp = {"customers": {"none": "소비재"}}
        self.assertIsNone(cv.section(dp))
        self.assertIsNone(cv.chart(dp))
        self.assertIsNone(cv.summary_item(dp))


class TestReport(unittest.TestCase):
    def test_section(self):
        sec = cv.section(DP)
        text = str(sec["blocks"])
        self.assertEqual(sec["h2"], "고객")
        self.assertIn("Applied Materials(Customer B)", text)
        self.assertIn("20~30%", text)
        self.assertIn("+5%p", text)
        self.assertIn("기타·미분해", text)

    def test_chart_marks_estimate(self):
        rows = cv.chart(DP)["rows"]
        self.assertEqual(rows[1]["bars"][0]["name"], "추정")
        self.assertEqual(rows[-1]["label"], "기타·미분해")
        self.assertEqual(len(rows), 3)


if __name__ == "__main__":
    unittest.main()
