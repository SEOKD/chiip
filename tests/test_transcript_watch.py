"""어닝콜 전문 신규 게재 감시 — 일정 누적·대기·발견·이미 정리·콜 반영 대기(마스터 지시 2026-10-30)"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))

import transcript_watch as tw  # noqa: E402

NOW = datetime(2026, 10, 30, 0, 0, tzinfo=timezone.utc)
CAL = {"events": [
    {"key": "NASDAQ_AAA", "ticker": "AAA", "name": "Aaa", "date": "2026-10-29", "utc": "2026-10-29T20:30:00Z", "period": "Q3 2026"},
    {"key": "NASDAQ_BBB", "ticker": "BBB", "name": "Bbb", "date": "2026-10-29", "utc": "2026-10-29T12:00:00Z", "period": "Q1 2027"},
    {"key": "NASDAQ_CCC", "ticker": "CCC", "name": "Ccc", "date": "2026-11-05", "utc": "2026-11-05T21:00:00Z", "period": "Q3 2026"},
    {"key": "NASDAQ_OLD", "ticker": "OLD", "name": "Old", "date": "2026-10-10", "utc": "2026-10-10T12:00:00Z", "period": "Q3 2026"}]}


class TestTranscriptWatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = {}
        self.p = [patch.object(tw.common, "load_state", lambda n, d=None: json.loads(json.dumps(self.state)) if self.state else (d if d is not None else {})),
                  patch.object(tw.common, "save_state", lambda n, d: self.state.update(json.loads(json.dumps(d)))),
                  patch.object(tw, "_ids", lambda: {"NASDAQ_AAA": "co-aaa"}),
                  patch.object(tw, "_tier", lambda cid: 0 if cid == "co-aaa" else 2),
                  patch.object(tw, "EARN", Path(self.tmp.name)),
                  patch.object(tw, "CAL", Path(self.tmp.name) / "cal.json")]
        (Path(self.tmp.name) / "cal.json").write_text(json.dumps(CAL), encoding="utf-8")
        for x in self.p:
            x.start()
        tw.common.save_state("transcripts", tw.refresh({}, NOW, CAL))

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def test_event_key(self):
        self.assertEqual(tw.event_key("Q1 2027"), "q1-2027")
        self.assertEqual(tw.event_key("FY 2026"), "q4-2026")
        self.assertIsNone(tw.event_key(None))

    def test_pending_only_after_call_and_within_window(self):
        st = tw.refresh(tw.common.load_state("transcripts"), NOW)
        keys = [r["key"] for r in tw.pending(st, NOW)]
        self.assertEqual(keys, ["NASDAQ_AAA", "NASDAQ_BBB"])   # 보유(tier 0) 먼저, 미래·만료 건 제외
        self.assertEqual(st["events"]["NASDAQ_OLD|q3-2026"]["status"], "expired")
        d = tw.due(NOW, st)
        self.assertTrue(d["check"])
        self.assertEqual(d["waiting"], 2)

    def test_put_marks_found_and_skips_already_covered(self):
        for n in (1, 2, 3):   # BBB는 콜 기준 ②·③을 이미 보냈다
            Path(self.tmp.name, f"20261029_BBB_{n}.txt").write_text("x", encoding="utf-8")
        out = Path(self.tmp.name) / "out.json"
        out.write_text(json.dumps({"found": [{"key": "NASDAQ_AAA", "event": "q3-2026", "paragraphs": 90, "qa": True},
                                             {"key": "NASDAQ_BBB", "event": "q1-2027", "paragraphs": 80, "qa": True}]}), encoding="utf-8")
        todo = tw.put(out, NOW)
        self.assertEqual([r["key"] for r in todo], ["NASDAQ_AAA"])
        self.assertEqual(todo[0]["scope"], "3단")
        self.assertEqual(self.state["events"]["NASDAQ_BBB|q1-2027"]["status"], "done")
        self.assertFalse(tw.due(NOW)["check"])   # 방금 확인 — 20분 안에는 다시 묻지 않는다
        self.assertTrue(todo[0]["feed"]["file"].endswith("20261030_AAA_4.txt"))   # ④ 인사이트 피드 = 전문 발견일(KST) 이름
        self.assertTrue(tw.done("NASDAQ_AAA", "q3-2026", now=NOW).startswith("미완료"))   # ④ 없이는 완료가 아니다
        self.assertEqual(len(tw.to_summarize(self.state)), 1)
        Path(self.tmp.name, "20261030_AAA_4.txt").write_text("x", encoding="utf-8")
        self.assertEqual(tw.done("NASDAQ_AAA", "q3-2026", now=NOW), "완료")
        self.assertEqual(tw.to_summarize(self.state), [])

    def test_summary_written_before_transcript_is_redone(self):
        """표시(--await)를 빠뜨려도 직전 확인보다 먼저 쓴 ②·③은 보도자료 기준으로 보고 콜 기준으로 다시 쓴다(2026-10-30 재점검 — MTZ)"""
        for n in (1, 2, 3):
            f = Path(self.tmp.name, f"20261029_BBB_{n}.txt")
            f.write_text("x", encoding="utf-8")
            os.utime(f, (NOW.timestamp() - 7200, NOW.timestamp() - 7200))
        self.state["last_check"] = datetime(2026, 10, 29, 23, 40, tzinfo=timezone.utc).isoformat()
        out = Path(self.tmp.name) / "out.json"
        out.write_text(json.dumps({"found": [{"key": "NASDAQ_BBB", "event": "q1-2027", "paragraphs": 80, "qa": True}]}), encoding="utf-8")
        todo = tw.put(out, NOW)
        self.assertEqual([r["key"] for r in todo], ["NASDAQ_BBB"])
        self.assertTrue(self.state["events"]["NASDAQ_BBB|q1-2027"]["await"])

    def test_done_with_no_feed_reason(self):
        out = Path(self.tmp.name) / "out.json"
        out.write_text(json.dumps({"found": [{"key": "NASDAQ_AAA", "event": "q3-2026", "paragraphs": 90}]}), encoding="utf-8")
        tw.put(out, NOW)
        self.assertEqual(tw.done("NASDAQ_AAA", "q3-2026", "종가 없음", NOW), "완료")
        self.assertEqual(self.state["events"]["NASDAQ_AAA|q3-2026"]["no_feed"], "종가 없음")

    def test_await_forces_rewrite_even_with_files(self):
        for n in (1, 2, 3):
            Path(self.tmp.name, f"20261029_BBB_{n}.txt").write_text("x", encoding="utf-8")
        self.assertTrue(tw.mark_await("NASDAQ_BBB", "q1-2027", NOW))
        out = Path(self.tmp.name) / "out.json"
        out.write_text(json.dumps({"found": [{"key": "NASDAQ_BBB", "event": "q1-2027", "paragraphs": 80}]}), encoding="utf-8")
        todo = tw.put(out, NOW)
        self.assertEqual([r["key"] for r in todo], ["NASDAQ_BBB"])
        self.assertEqual(todo[0]["scope"], "② 뉴팩트")
        self.assertEqual(sorted(todo[0]["files"]), [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
