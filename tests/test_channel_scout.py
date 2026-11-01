"""데이터 파이프라인 채널 탐색 장부 (마스터 지시 2026-11-01)"""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import channel_scout as cs  # noqa: E402

CFG = cs.config()
OK = {"channel": "SEC Financial Statement Data Sets", "area": "공시·규제", "access": "공개 파일", "robots": "허용", "terms": "허용", "needs": "없음", "decision": "채택 제안", "reason": "무료 분기 재무"}


class TestScout(unittest.TestCase):
    def test_complete_row_passes(self):
        self.assertEqual(cs.problems(OK, CFG), [])

    def test_terms_result_is_required(self):
        self.assertTrue(cs.problems({**OK, "robots": ""}, CFG))
        self.assertTrue(cs.problems({**OK, "terms": ""}, CFG))
        self.assertTrue(cs.problems({**OK, "reason": ""}, CFG))

    def test_blocked_channel_cannot_be_proposed(self):
        self.assertTrue(cs.problems({**OK, "robots": "금지"}, CFG))
        self.assertTrue(cs.problems({**OK, "terms": "미확인"}, CFG))
        self.assertEqual(cs.problems({**OK, "robots": "금지", "decision": "기각"}, CFG), [])

    def test_paid_channel_stays_a_candidate(self):
        for need in ("유료", "키 발급", "로그인"):
            self.assertTrue(cs.problems({**OK, "needs": need}, CFG))
            self.assertTrue(cs.problems({**OK, "needs": need, "decision": "보류"}, CFG))
            self.assertEqual(cs.problems({**OK, "needs": need, "decision": "승인 대기"}, CFG), [])
        self.assertTrue(cs.problems({**OK, "decision": "승인 대기"}, CFG))

    def test_empty_search_needs_a_reason(self):
        self.assertEqual(cs.problems({"channel": "없음", "decision": "없음", "reason": "공급망 분야 무료 원천 3곳 확인"}, CFG), [])
        self.assertTrue(cs.problems({"channel": "없음", "decision": "없음", "reason": ""}, CFG))

    def test_missing_run_is_marked_incomplete(self):
        self.assertEqual(cs.audit("2026-11-01", [], True)["decision"], "미완료")
        self.assertEqual(cs.audit("2026-11-01", [], False)["decision"], "미실행")
        self.assertIsNone(cs.audit("2026-11-01", [{"date": "2026-11-01", "decision": "보류"}], True))

    def test_marker_rows_do_not_count_as_done(self):
        self.assertFalse(cs.recorded("2026-11-01", [{"date": "2026-11-01", "decision": "미완료"}]))

    def test_run_past_midnight_belongs_to_previous_day(self):
        self.assertEqual(cs.run_day(datetime(2026, 11, 2, 0, 40)), "2026-11-01")
        self.assertEqual(cs.run_day(datetime(2026, 11, 1, 23, 20)), "2026-11-01")

    def test_each_day_is_judged_once(self):
        self.assertEqual(list(cs.days_to_check(None, date(2026, 11, 3), "2026-11-01")), ["2026-11-01", "2026-11-02"])
        self.assertEqual(list(cs.days_to_check("2026-11-01", date(2026, 11, 3), "2026-11-01")), ["2026-11-02"])
        self.assertEqual(list(cs.days_to_check("2026-11-02", date(2026, 11, 3), "2026-11-01")), [])

    def test_focus_rotates_through_areas(self):
        got = {cs.focus(f"2026-11-{d:02d}", CFG["areas"]) for d in range(1, 11)}
        self.assertEqual(len(got), len(CFG["areas"]))


if __name__ == "__main__":
    unittest.main()
