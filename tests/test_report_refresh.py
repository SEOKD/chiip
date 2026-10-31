"""어닝콜 전문 반영 재발행 (마스터 지시 2026-10-31)"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import report_refresh as rr  # noqa: E402

TODAY = date(2026, 10, 31)


class Base(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.d = Path(t.name)
        self.rep, self.co, self.dl = self.d / "rep", self.d / "co", self.d / "delivery"
        self.rep.mkdir()
        self.dl.mkdir()
        self.ev = self.d / "transcripts.json"
        self.log([("2026-10-30", "us-a", "AAA", "outputs/tenbagger/reports/20261030_AAA.html")])
        self.pack("us-a", "2026-07-30")

    def log(self, rows):
        body = "date,id,ticker,html,view\n" + "".join(f"{a},{b},{c},{d},판단\n" for a, b, c, d in rows)
        (self.rep / "log.csv").write_text(body, encoding="utf-8")

    def pack(self, cid, call):
        (self.co / cid).mkdir(parents=True, exist_ok=True)
        (self.co / cid / "datapack.json").write_text(json.dumps({"call": {"date": call}}), encoding="utf-8")

    def events(self, status="wait", date_="2026-10-29", key="NASDAQ_AAA"):
        self.ev.write_text(json.dumps({"events": {"x": {"key": key, "event": "q3-2026", "ticker": "AAA", "id": "us-a", "date": date_, "status": status}}}), encoding="utf-8")

    def status(self):
        return rr.status(TODAY, self.rep, self.co, self.ev)


class TestStatus(Base):
    def test_waits_then_due_when_transcript_appears(self):
        self.events("wait")
        self.assertEqual(self.status()[0]["state"], "대기")
        self.assertEqual(rr.due(today=TODAY, root=self.rep, companies=self.co, events_file=self.ev), [])
        self.events("found")
        self.assertEqual(self.status()[0]["state"], "재발행")
        self.events("done")
        self.assertEqual(self.status()[0]["stem"], "20261030_AAA")

    def test_expired_is_listed_not_due(self):
        self.events("expired")
        self.assertEqual(self.status()[0]["state"], "만료")

    def test_report_already_using_that_call_is_skipped(self):
        self.pack("us-a", "2026-10-29")
        self.events("found")
        self.assertEqual(self.status(), [])

    def test_next_quarter_call_after_report_is_skipped(self):
        self.events("found", date_="2026-11-12")
        self.assertEqual(self.status(), [])

    def test_korea_waits_for_nothing(self):
        self.events("found", key="XKRX_000660")
        self.assertEqual(self.status(), [])

    def test_old_report_is_left_alone(self):
        self.log([("2026-10-01", "us-a", "AAA", "outputs/tenbagger/reports/20261001_AAA.html")])
        self.events("found", date_="2026-09-30")
        self.assertEqual(self.status(), [])

    def test_one_reissue_per_call(self):
        self.events("found")
        (self.rep / "reissue.csv").write_text("time,stem,ticker,event,note\nt,20261030_AAA,AAA,q3-2026,반영\n", encoding="utf-8")
        self.assertEqual(self.status(), [])


class TestDone(Base):
    def setUp(self):
        super().setUp()
        (self.rep / "20261030_AAA.json").write_text(json.dumps({"ticker": "AAA", "sections": [{"h2": "재발행 기록 — 어닝콜 전문 반영"}]}, ensure_ascii=False), encoding="utf-8")
        (self.dl / "20261030_AAA.json").write_text(json.dumps({"artifact": {"status": "ok", "url": "https://a"}, "notion": {"status": "ok", "page": "https://n"}, "telegram": {"sent": True, "at": "2026-10-30T01:00:00+09:00"}}), encoding="utf-8")

    def test_start_keeps_links_and_reopens_publishing(self):
        self.assertEqual(rr.start("20261030_AAA", self.dl), {"artifact_url": "https://a", "notion_page": "https://n"})
        st = json.loads((self.dl / "20261030_AAA.json").read_text(encoding="utf-8"))
        self.assertEqual((st["artifact"]["status"], st["notion"]["status"]), ("pending", "pending"))

    def test_done_needs_new_telegram(self):
        rr.start("20261030_AAA", self.dl)
        with self.assertRaises(SystemExit):
            rr.done("20261030_AAA", "q3-2026", "반영", self.rep, self.dl)
        p = self.dl / "20261030_AAA.json"
        st = json.loads(p.read_text(encoding="utf-8"))
        st["telegram"] = {"sent": True, "at": "2099-01-01T00:00:00+09:00"}
        p.write_text(json.dumps(st), encoding="utf-8")
        self.assertEqual(rr.done("20261030_AAA", "q3-2026", "반영", self.rep, self.dl), "완료")
        self.assertIn(("20261030_AAA", "q3-2026"), rr.reissued(self.rep / "reissue.csv"))

    def test_done_needs_note_section(self):
        (self.rep / "20261030_AAA.json").write_text(json.dumps({"sections": []}), encoding="utf-8")
        with self.assertRaises(SystemExit):
            rr.done("20261030_AAA", "q3-2026", "반영", self.rep, self.dl)


class TestPublish(unittest.TestCase):
    def test_reissue_sends_again_marked_as_revision(self):
        import publish_tenbagger as pt
        st = {"stem": "x", "ticker": "AAA", "company": "에이", "github": {"md": "https://g"}, "artifact": {"status": "ok", "url": "https://a"},
              "notion": {"status": "ok", "page": "https://n"}, "telegram": {"sent": True, "notion_ok": True}}
        with mock.patch.object(pt, "load", return_value=st), mock.patch.object(pt, "save"), mock.patch.object(pt, "log"):
            self.assertIn("skipped", pt.send("x.json", "캡션", dry=True))
            res = pt.send("x.json", "캡션", dry=True, reissue=True)
        self.assertTrue(res["text"].startswith("[수정판"))
        self.assertIn("https://a", res["text"])


if __name__ == "__main__":
    unittest.main()
