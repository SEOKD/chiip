"""대만·홍콩 IR 수집 (마스터 지시 2026-11-01)"""
import sys
import unittest
import unittest.mock
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import pulse  # noqa: E402
from pollers import tw_hk_ir as ir  # noqa: E402

C = {"market": "tw"}
PAGE = '''<a href="/files/3Q26Presentation.pdf">3Q26 Earnings Conference Presentation</a>
<a href="/files/3Q26transcript.pdf">3Q26 Transcript</a>
<a href="/files/2Q26transcript.pdf">2Q26 Transcript</a>
<a href="/zh/q3qa.pdf">2026年第三季 法說會問答</a>
<a href="/about.pdf">Company Profile</a>'''


class TestScan(unittest.TestCase):
    def test_reads_documents_by_kind(self):
        got = {(d["kind"], d["period"]) for d in ir.scan(PAGE, "https://x.example/ir/", C)}
        self.assertIn(("transcript", "FY2026Q3"), got)
        self.assertIn(("presentation", "FY2026Q3"), got)
        self.assertIn(("qa", "FY2026Q3"), got)
        self.assertEqual(len(got), 4)

    def test_only_latest_period_is_new(self):
        rows = ir.scan(PAGE, "https://x.example/ir/", C)
        self.assertNotIn("FY2026Q2", {d["period"] for d in ir.fresh_docs(rows, date(2026, 11, 2))})

    def test_company_names_come_first(self):
        rows = ir.scan('<a href="/a.pdf">Q3 2026 Call Memo</a>', "https://x.example/ir/", {"kinds": {"qa": "Call Memo"}})
        self.assertEqual(rows[0]["kind"], "qa")

    def test_periods(self):
        self.assertEqual(ir.period("3Q26 results", "u"), "FY2026Q3")
        self.assertEqual(ir.period("2026年第三季法說會", "u"), "FY2026Q3")
        self.assertEqual(ir.period("2026 Q2 Earnings", "u"), "FY2026Q2")


class TestUnofficial(unittest.TestCase):
    PAGE = '<a href="/quote/tpe/2382/transcripts/319969-q1-2025/">Q1</a><a href="/quote/tpe/2382/transcripts/343840-q2-2025/">Q2</a>'

    def test_latest_transcript(self):
        self.assertEqual(ir.transcript_links(self.PAGE)[-1][1], "343840-q2-2025")

    def test_first_run_is_baseline(self):
        items, cs = [], {}
        with unittest.mock.patch.object(ir.qa, "fetch", lambda u, t=20: self.PAGE.encode()), unittest.mock.patch.object(ir.qa, "_text", lambda b: b.decode()):
            ir.unofficial("x", {"market": "tw", "code": "2382"}, cs, items, True)
        self.assertEqual((items, cs["sa_latest"]), ([], "FY2025Q2"))


class TestPulseClass(unittest.TestCase):
    def test_classes(self):
        self.assertEqual(pulse.class_of("src-tw-hk-ir-qa"), "IR 질의응답")
        self.assertEqual(pulse.class_of("src-tw-hk-ir-docs"), "IR 자료")

    def test_all_universe_companies_listed(self):
        self.assertGreaterEqual(len(ir.config()["companies"]), 25)


if __name__ == "__main__":
    unittest.main()
