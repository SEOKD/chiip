"""노션 Exclusive Source 단서 장부 (마스터 지시 2026-11-02)"""
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import exclusive_leads as ex  # noqa: E402

NOW = datetime(2026, 11, 2, 9, 0, tzinfo=ex.common.KST)
LEAD = {"id": "FI-0001", "title": "시험 단서", "entities": ["co-skhynix"], "names": ["HBM4"], "insider_like": True, "must": ["HBM4", "엔비디아"], "evidence": []}
ROW = {"fi_id": "FI-0001", "publicly_confirmed_at": ""}


class TestLines(unittest.TestCase):
    def test_company_or_name_finds_lead(self):
        data = {"page": "p", "leads": [LEAD]}
        self.assertEqual(len(ex.lines("co-skhynix", "co-skhynix", data, [ROW])), 1)
        self.assertEqual(len(ex.lines("hbm4", "hbm4", data, [ROW])), 1)
        self.assertEqual(ex.lines("co-tsmc", "co-tsmc", data, [ROW]), [])

    def test_line_keeps_unconfirmed_and_insider_marks(self):
        s = ex.line(dict(LEAD, evidence=[{"verdict": "지지"}, {"verdict": "상충"}]), ROW, "p")
        self.assertIn("F1", s)
        self.assertIn("공개 미확인(지지 1·상충 1·맥락 0)", s)
        self.assertIn("invest·public·Portfolio·텐배거 리포트 금지", s)

    def test_confirmed_line(self):
        self.assertIn("공개 확인", ex.line({**LEAD, "insider_like": False}, {"publicly_confirmed_at": "2026-11-03"}, "p"))

    def test_line_marks_top_secret(self):
        self.assertIn("웹 대조 금지", ex.line(LEAD, ROW, "p"))

    def test_unexplained_until_marked_and_again_on_edit(self):
        data = {"leads": [dict(LEAD, block="a")]}
        self.assertEqual(len(ex.unexplained(data)), 1)
        ex.explained("FI-0001", data)
        self.assertEqual(ex.unexplained(data), [])
        data["leads"][0]["block"] = "b"
        self.assertEqual(len(ex.unexplained(data)), 1)

    def test_insider_ids(self):
        self.assertEqual(ex.insider({"leads": [LEAD, {"id": "FI-0002"}]}), {"FI-0001"})


class TestCorroboration(unittest.TestCase):
    def test_conflict_beats_support(self):
        self.assertEqual(ex.corroboration({"evidence": [{"verdict": "지지"}, {"verdict": "상충"}]}), "contradicted")
        self.assertEqual(ex.corroboration({"evidence": [{"verdict": "지지"}]}), "corroborated")
        self.assertEqual(ex.corroboration({"evidence": [{"verdict": "맥락"}]}), "pending")


class TestCollect(unittest.TestCase):
    def entry(self, title, link="u1"):
        return {"title": title, "link": link, "date": "", "publisher": "매체"}

    def test_all_must_terms_needed(self):
        self.assertEqual(ex.collect(LEAD, [self.entry("HBM4 시장 전망")], set(), set()), [])
        self.assertEqual(len(ex.collect(LEAD, [self.entry("HBM4 엔비디아 납품")], set(), set())), 1)

    def test_same_title_and_known_url_are_skipped(self):
        seen = set()
        got = ex.collect(LEAD, [self.entry("HBM4 엔비디아 납품 - 갑"), self.entry("HBM4 엔비디아 납품 - 을", "u2"), self.entry("HBM4 엔비디아 수율", "u3")], seen, {"u3"})
        self.assertEqual([x["url"] for x in got], ["u1"])

    def test_per_lead_cap(self):
        got = ex.collect(LEAD, [self.entry(f"HBM4 엔비디아 {i}", str(i)) for i in range(9)], set(), set())
        self.assertEqual(len(got), ex.PER_LEAD)


class TestStatus(unittest.TestCase):
    def test_hold_stops_gate_reopening(self):
        st = {"pending": [{"fi": "FI-0001"}]}
        with mock.patch.object(ex.common, "load_state", lambda *a: st):
            self.assertFalse(ex.status(NOW)["due"])   # 웹 대조 금지(2026-11-11)
            with mock.patch.object(ex, "WEB_CHECK", True):
                self.assertTrue(ex.status(NOW)["due"])
            st["hold"] = ex.common.iso(NOW.replace(hour=10))
            self.assertFalse(ex.status(NOW)["due"])

    def test_nothing_pending(self):
        with mock.patch.object(ex.common, "load_state", lambda *a: {}):
            self.assertFalse(ex.status(NOW)["due"])


class TestJudge(unittest.TestCase):
    def judge(self, verdict):
        data = {"page": "p", "leads": [dict(LEAD, evidence=[])]}
        rows = [dict(ROW, corroboration="pending")]
        st = {"pending": [{"fi": "FI-0001", "url": "u", "title": "기사"}]}
        with mock.patch.object(ex.common, "load_state", lambda *a: st), mock.patch.object(ex.common, "save_state"), mock.patch.object(ex, "save"), mock.patch.object(ex, "write_index"):
            msg = ex.judge("FI-0001", "u", verdict, "메모", "2026-11-02", data, (["fi_id", "corroboration"], rows))
        return msg, data["leads"][0], rows[0], st

    def test_support_alerts_and_updates_index(self):
        msg, lead, row, st = self.judge("지지")
        self.assertIn("공개 근거 지지", msg)
        self.assertEqual((row["corroboration"], len(lead["evidence"]), st["pending"]), ("corroborated", 1, []))

    def test_context_is_kept_quietly(self):
        msg, lead, row, _ = self.judge("맥락")
        self.assertIsNone(msg)
        self.assertEqual((row["corroboration"], len(lead["evidence"])), ("pending", 1))

    def test_unrelated_is_dropped(self):
        msg, lead, _, st = self.judge("무관")
        self.assertIsNone(msg)
        self.assertEqual((lead["evidence"], st["pending"]), ([], []))

    def test_bad_verdict_stops(self):
        with self.assertRaises(SystemExit):
            ex.judge("FI-0001", "u", "확인", "메모", "2026-11-02", {"leads": [LEAD]})


class TestSync(unittest.TestCase):
    PAGE = "26.10.07\n\n■첫 단서\n\n- 내용 하나\n\n26.10.16\n\n<b>■둘째 단서</b>\n\n- 내용 둘\n"

    def data(self):
        return {"leads": [{"id": "FI-0001", "key": ex.digest("첫 단서"), "block": ""}]}

    def test_new_item_is_found(self):
        self.assertEqual(ex.sync(self.PAGE, self.data())[0], ["둘째 단서"])

    def test_first_pass_sets_baseline_then_edit_is_seen(self):
        d = self.data()
        self.assertEqual(ex.sync(self.PAGE, d)[1], [])
        self.assertEqual(ex.sync(self.PAGE, d)[1], [])
        self.assertEqual(ex.sync(self.PAGE.replace("내용 하나", "내용 하나\n- (26.11.02) 추가"), d)[1], ["FI-0001"])

    def test_escaped_newlines_from_saved_fetch(self):
        self.assertEqual(ex.sync(self.PAGE.replace("\n", "\\n"), self.data())[0], ["둘째 단서"])


class TestAdd(unittest.TestCase):
    def test_new_lead_is_f1_with_next_id(self):
        data, rows = {"leads": []}, [{"fi_id": "FI-0008"}]
        spec = {"notion_title": "새 단서", "title": "새", "entities": ["co-samsung"], "source_class": "A-memory-maker", "reliability": "C3", "topics": ["x"], "insider_like": False}
        self.assertEqual(ex.add(spec, NOW, data, [], rows), "FI-0009")
        self.assertEqual((rows[-1]["disclosure_class"], rows[-1]["outcome"]), ("F1", "pending"))
        self.assertTrue(rows[-1]["f1_converted_at"])
        self.assertNotIn("reliability", data["leads"][0])


class TestStore(unittest.TestCase):
    def test_round_trip_keeps_comment_and_korean(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x" / "leads.yaml"
            ex.save({"page": "p", "leads": [LEAD]}, p)
            self.assertTrue(p.read_text(encoding="utf-8").startswith("# 노션"))
            self.assertEqual(ex.load(p)["leads"][0]["title"], "시험 단서")

    def test_ledger_stays_local(self):
        for p in (ex.LEADS, ex.INDEX):
            self.assertEqual(subprocess.run(["git", "check-ignore", "-q", str(p)], cwd=ROOT).returncode, 0)

    def test_missing_index_is_empty(self):
        self.assertEqual(ex.index(Path("없는파일.csv")), (ex.COLUMNS, []))

    def test_ledger_holds_no_source_wording(self):
        if not ex.LEADS.exists():
            self.skipTest("장부는 이 PC에만 있다")
        text = ex.LEADS.read_text(encoding="utf-8")
        for word in ("관계자", "파견자", "파트장", "정책과"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
