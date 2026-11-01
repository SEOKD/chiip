"""일본 어닝콜 전사 확인 (마스터 지시 2026-11-02)"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))

import jp_tv_docs as jt  # noqa: E402

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 2, 9, 0, tzinfo=KST)
DOC = {"category": {"id": "call_transcript"}, "title": "Q2 2027 (Q&A)", "reported": NOW.timestamp() - 86400 * 4,
       "views": [{"id": "urn:t", "type": "transcript"}, {"id": "urn:s", "type": "summary"}]}
OLD = dict(DOC, reported=NOW.timestamp() - 86400 * 90)
SLIDE = dict(DOC, category={"id": "slides"})


def state(n=1, day="2026-10-29"):
    return {"targets": {f"c{i}": {"id": f"c{i}", "symbol": f"TSE:{1000 + i}", "code": str(1000 + i), "name": "x", "date": day, "tier": i % 3, "status": "wait", "tries": 0,
                                  "next_at": NOW.isoformat()} for i in range(n)}}


class TestBatch(unittest.TestCase):
    def test_at_most_three_per_run(self):
        self.assertEqual(len(jt.batch(state(66), NOW)), jt.MAX_PER_RUN)

    def test_priority_first(self):
        self.assertEqual({r["tier"] for r in jt.batch(state(9), NOW)}, {0})

    def test_waits_between_checks(self):
        st = dict(state(2), last_check=(NOW - timedelta(minutes=5)).isoformat())
        self.assertFalse(jt.status(NOW, st)["due"])
        st["last_check"] = (NOW - timedelta(minutes=25)).isoformat()
        self.assertEqual(len(jt.status(NOW, st)["check"]), 2)


class TestRecord(unittest.TestCase):
    def rec(self, items):
        r = state()["targets"]["c0"]
        jt.record(r, {"items": items}, NOW)
        return r

    def test_transcript_found_with_views(self):
        r = self.rec([DOC])
        self.assertEqual(r["status"], "found")
        self.assertEqual((r["docs"][0]["summary"], r["docs"][0]["qa"]), ("urn:s", True))

    def test_old_quarter_and_slides_do_not_count(self):
        r = self.rec([OLD, SLIDE])
        self.assertEqual(r["status"], "wait")
        self.assertEqual(datetime.fromisoformat(r["next_at"]), NOW + timedelta(hours=6))

    def test_backoff_grows(self):
        r = state()["targets"]["c0"]
        r["tries"] = 3
        jt.record(r, {"items": []}, NOW)
        self.assertEqual(datetime.fromisoformat(r["next_at"]), NOW + timedelta(hours=48))


class TestRefresh(unittest.TestCase):
    def setUp(self):
        for name, val in (("companies", lambda: {"co-x": {"code": "6857", "en": "X"}}), ("tier", lambda c: 0)):
            p = mock.patch.object(jt, name, val)
            p.start()
            self.addCleanup(p.stop)

    def test_adds_target(self):
        st = jt.refresh({}, NOW, {"co-x": "2026-10-28", "co-unknown": "2026-10-28"})
        self.assertEqual(list(st["targets"]), ["co-x"])
        self.assertEqual(st["targets"]["co-x"]["symbol"], "TSE:6857")

    def test_expires_after_wait(self):
        st = jt.refresh({}, NOW, {"co-x": "2026-10-20"})
        self.assertEqual(st["targets"]["co-x"]["status"], "expired")

    def test_next_quarter_reopens(self):
        st = jt.refresh({}, NOW, {"co-x": "2026-10-28"})
        st["targets"]["co-x"]["status"] = "done"
        jt.refresh(st, NOW, {"co-x": "2026-10-30"})
        self.assertEqual(st["targets"]["co-x"]["status"], "wait")


class TestPut(unittest.TestCase):
    def test_put_returns_found(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "out.json"
            p.write_text(json.dumps({"TSE:1000": {"items": [DOC]}}), encoding="utf-8")
            st = state()
            with mock.patch.object(jt.common, "load_state", lambda *a: st), mock.patch.object(jt.common, "save_state", lambda *a: None):
                got = jt.put(p, NOW)
        self.assertEqual([r["id"] for r in got], ["c0"])


if __name__ == "__main__":
    unittest.main()
