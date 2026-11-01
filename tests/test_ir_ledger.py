"""IR 전문·Q&A 누락 방지 (마스터 지시 2026-11-01 — 도쿄일렉트론 FY27Q2 전문)"""
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import ir_ledger as il  # noqa: E402
from pollers import common, jp_ir_audit, jp_ir_docs, jp_ir_qa  # noqa: E402

NOW = datetime(2026, 11, 1, 19, 0, tzinfo=common.KST)
ITEM = {"source_class": "IR 질의응답", "url": "https://x/fy27q2transcript-j.pdf", "title": "TEL 전문"}


def fresh():
    return {"docs": {}}


class TestLedger(unittest.TestCase):
    def test_new_document_is_due(self):
        st = fresh()
        self.assertEqual(il.track([ITEM], NOW, st), 1)
        self.assertEqual(len(il.due(NOW, st)), 1)

    def test_same_file_at_two_paths_counts_once(self):
        st = fresh()
        a = {**ITEM, "entities_matched": ["co-tel"], "url": "https://t/a/fy27q2transcript-j.pdf"}
        b = {**ITEM, "entities_matched": ["co-tel"], "url": "https://t/b/fy27q2transcript-j.pdf"}
        self.assertEqual(il.track([a, b], NOW, st), 1)

    def test_other_classes_are_ignored(self):
        st = fresh()
        il.track([{"source_class": "공시", "url": "u"}], NOW, st)
        self.assertEqual(st["docs"], {})

    def test_being_offered_is_not_done(self):
        st = fresh()
        il.track([ITEM], NOW, st)
        il.offered([ITEM["url"]], NOW, st)
        self.assertEqual(il.due(NOW + timedelta(hours=1), st), [])
        self.assertEqual(len(il.due(NOW + timedelta(hours=4), st)), 1)   # 실렸어도 기록이 없으면 다시 싣는다
        self.assertEqual(st["docs"][ITEM["url"]]["tries"], 1)

    def test_done_stops_retries(self):
        st = fresh()
        il.track([ITEM], NOW, st)
        il.done(ITEM["url"], "outputs/article/earnings/x_2.txt", NOW, st)
        self.assertEqual(il.due(NOW + timedelta(days=2), st), [])
        self.assertEqual(il.overdue(NOW + timedelta(days=2), st), [])

    def test_done_requires_a_note(self):
        st = fresh()
        il.track([ITEM], NOW, st)
        with self.assertRaises(SystemExit):
            il.done(ITEM["url"], " ", NOW, st)

    def test_overdue_after_a_day(self):
        st = fresh()
        il.track([ITEM], NOW, st)
        self.assertEqual(il.overdue(NOW + timedelta(hours=23), st), [])
        self.assertEqual(len(il.overdue(NOW + timedelta(hours=25), st)), 1)


class TestCurrentDocs(unittest.TestCase):
    TODAY = date(2026, 11, 1)

    def run_it(self, new, qa=None):
        return jp_ir_qa.current(new, qa or dict(new), self.TODAY, 7, jp_ir_docs.period_of, jp_ir_docs.doc_date)

    def test_tel_case_keeps_only_latest_period(self):
        new = [("https://t/fy27q2transcript-j.pdf", "トランスクリプト（1.4MB）"), ("https://t/fy27q1transcript-j.pdf", "トランスクリプト（1.4MB）"), ("https://t/fy2009q3saekij.pdf", "決算概要")]
        self.assertEqual(self.run_it(new), {"https://t/fy27q2transcript-j.pdf"})

    def test_misread_future_period_is_ignored(self):
        new = [("https://t/fy27q2transcript-j.pdf", "トランスクリプト"), ("https://t/fy2058q4.pdf", "決算"), ("https://t/fy26q1transcript-j.pdf", "トランスクリプト")]
        self.assertEqual(self.run_it(new), {"https://t/fy27q2transcript-j.pdf"})

    def test_guide_pages_are_not_documents(self):
        self.assertEqual(self.run_it([("https://t/ir/summary.html", "決算サマリー")]), set())

    def test_dated_documents_use_the_date(self):
        new = [("https://t/qa_20261030.pdf", "質疑応答"), ("https://t/qa_20250130.pdf", "質疑応答")]
        self.assertEqual(self.run_it(new), {"https://t/qa_20261030.pdf"})

    def test_many_undated_documents_are_archive(self):
        new = [(f"https://t/d{i}.pdf", "質疑応答") for i in range(5)]
        self.assertEqual(self.run_it(new), set())
        self.assertEqual(len(self.run_it(new[:2])), 2)


class TestSavedAt(unittest.TestCase):
    def test_pulse_reads_saved_time(self):
        src = (ROOT / "radar" / "pulse.py").read_text(encoding="utf-8")
        self.assertIn('it.get("saved_at") or it.get("detected_at")', src)
        self.assertIn('it["saved_at"]', (ROOT / "radar" / "pollers" / "common.py").read_text(encoding="utf-8"))


class TestAudit(unittest.TestCase):
    def test_states(self):
        d = {"doc_pages": ["p"], "seen": ["https://t/fy27q2transcript-j.pdf", "https://t/fy27q2presentations-j.pdf"]}
        r = jp_ir_audit.row("co-tel", {}, d, {}, {})
        self.assertEqual((r["state"], r["latest_period"]), ("전문·Q&A 있음", "FY2027Q2"))
        self.assertEqual(jp_ir_audit.row("x", {}, {}, {}, {})["state"], "자료실 미발견")
        self.assertEqual(jp_ir_audit.row("x", {}, {"doc_pages": ["p"], "seen": ["https://t/fy2058q4x-transcript.pdf"]}, {}, {}, year=2026)["state"], "기간 판독 실패")
        d2 = {"doc_pages": ["p"], "seen": ["https://t/fy27q2presentations-j.pdf"]}
        self.assertEqual(jp_ir_audit.row("x", {}, d2, {}, {})["state"], "전문·Q&A 없음")


if __name__ == "__main__":
    unittest.main()
