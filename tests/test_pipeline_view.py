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
        self.assertEqual(self.rows(sec, "수주·파이프라인 진척")[0][2], "비공개")   # 진척은 '비공개'(2026-11-13)
        self.assertEqual(self.rows(sec, "진척도별 수익")[0][2:6], ["미확인", "미확인", "$1.00B", "미확인"])
        self.assertEqual(self.rows(sec, "합계")[0][4], "미확인")
        self.assertFalse(any("남는 이익" in str(b.get("text")) for b in sec["blocks"]))

    def test_partial_unknown_is_marked_in_total(self):
        sec = pv.report_section(dp(item(), item(name="B", progress="미확인")))
        self.assertIn("미확인 1건", self.rows(sec, "합계")[0][2])

    def test_undisclosed_amount_and_overlapping_target(self):
        sec = pv.report_section(dp(item(status="파이프라인", total="미확인", progress="미확인"), item(name="목표 모델", status="파이프라인", no_sum=True)))
        self.assertIn("건별 확정 수주 금액은 공개되지 않았다", sec["blocks"][0]["text"])
        self.assertIn("합계에서 뺐다", sec["blocks"][0]["text"])
        self.assertEqual(self.rows(sec, "진척도별 수익")[0][4], "미확인")
        self.assertEqual(self.rows(sec, "합계")[0][:2], ["**미확정 합계**", "미확인"])

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


class TestSummaryLayout(unittest.TestCase):
    """'수주는 어디까지 왔나?'·본문 표 표기(마스터 지시 2026-11-13 — 계산은 그대로)"""

    def d(self):
        return dp(item(name="잔고", kind="backlog", total=2.934, progress="미확인"),
                  item(name="C MOU", status="MOU", total="미확인", progress="미확인", start=None, end=None),
                  item(name="Carina", region="인도네시아", total=0.42, progress=0.0, start="2027-06", end="2029-11", included_in="신규 $0.80B", note="7세대 드릴십"),
                  item(name="Capella", region="말레이시아 연장", total=0.041, progress=0.0, start=None, end=None),
                  reported_backlog=2.934, backlog_label="남은 계약(6월 말)", new_since={"label": "8월 이후 신규 약", "total": 0.8}, summary="2027 미계약 15% 미만")

    def test_summary_lines(self):
        L = pv.summary_lines(self.d())
        self.assertEqual(L, ["남은 계약 $2.93B(6월 말) + 8월 이후 신규 약 $0.80B",
                             "- Carina(인도네시아) — 확정 · $0.42B · 진척 0% · 착수 전 (신규 $0.80B에 포함)",
                             "- Capella(말레이시아 연장) — 확정 · $0.04B · 진척 0%",
                             "- C MOU — 미확정", "2027 미계약 15% 미만"])
        self.assertNotIn("7세대", "".join(L))   # 괄호 설명은 본문 비고로
        self.assertNotIn("미확인", pv.summary_item(self.d())["a"])

    def test_body_table_grouped_by_status(self):
        t = next(b for b in pv.section3(self.d())["blocks"] if b.get("title") == "수주 목록")
        self.assertEqual(t["headers"], ["상태", "계약", "계약 총액", "진척", "기간", "비고"])
        self.assertEqual([r[0] for r in t["rows"]], ["확정", "확정", "확정", "MOU"])
        self.assertIn("7세대 드릴십", t["rows"][1][5])
        self.assertEqual(t["rows"][3][2:4], ["금액 비공개", "비공개"])

    def test_terms(self):
        sec = pv.report_section(dp(item()))
        h = next(b for b in sec["blocks"] if b.get("title") == "진척도별 수익")["headers"]
        self.assertEqual(h[2:], ["인식된 매출", "인식된 이익", "계약 총액", "완료 시 이익"])


class TestLadder(unittest.TestCase):
    """확실성 사다리(마스터 지시 2026-11-08 — 시각물 직관성)"""

    def test_chart_groups_by_certainty(self):
        sec = pv.section3(dp(item(), item(name="B MOU", status="MOU", total="미확인", progress="미확인", start=None, end=None)))
        ch = next(b["chart"] for b in sec["blocks"] if b["type"] == "chart")
        self.assertEqual(ch["kind"], "pipeline")
        self.assertEqual([r["status"] for r in ch["rows"]], ["확정", "MOU"])
        self.assertIn("확정", ch["fmt"])
        self.assertNotIn("MOU·파이프라인", ch["fmt"])   # 금액을 모르는 단계는 합계를 쓰지 않는다
        sys.path.insert(0, str(ROOT / "radar"))
        import report_html as rh
        svg = rh.chart_pipeline(ch)
        self.assertIn("금액 비공개", svg)
        self.assertLess(svg.index("확정 · 1건"), svg.index("MOU·파이프라인 · 1건"))   # 확실한 단계가 위


if __name__ == "__main__":
    unittest.main()
