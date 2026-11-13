"""알파 상승 리포트 갱신 대기열·자료 풀이·경기순환 보정·안전마진 표기 (마스터 지시 2026-11-13, ADR-022)"""
import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
import alpha_refresh as A  # noqa: E402
import decision  # noqa: E402
import item_notes  # noqa: E402
import plus  # noqa: E402

KST = timezone(timedelta(hours=9))


def make_root(tmp, rep_date="2026-10-20", alpha=5.0):
    root = Path(tmp)
    with (root / "log.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "id", "ticker", "html", "view"])
        w.writerow([rep_date, "co-x", "XX", f"outputs/tenbagger/reports/{rep_date.replace('-', '')}_XX.html", "v"])
    (root / f"{rep_date.replace('-', '')}_XX.json").write_text(json.dumps({"verdict": {"alpha": alpha, "price": 10, "rating": "Buy"}}), encoding="utf-8")
    return root


class TestRefresh(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_root(self.tmp.name)
        self.state = Path(self.tmp.name) / "state.json"

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self, total, scored="20261110", delta=0.0):
        return {"co-x": {"total": total, "scored_on": scored, "name": "X", "delta": delta}}

    def test_rise_then_confirm_next_scoring(self):
        t0 = datetime(2026, 11, 10, 9, tzinfo=KST)
        self.assertEqual(A.scan(t0, self.root, self.state, self.rows(6.2)), (1, 0))   # 첫 충족 = 관찰
        self.assertIn("관찰", A.alert_line("co-x", self.state))
        self.assertEqual(A.scan(t0 + timedelta(hours=1), self.root, self.state, self.rows(6.2)), (0, 0))   # 같은 산정 — 아직
        self.assertEqual(A.scan(t0 + timedelta(days=3), self.root, self.state, self.rows(6.1, "20261113")), (0, 1))
        self.assertIn("대기열 등록", A.alert_line("co-x", self.state))

    def test_spike_reverted_drops_watch(self):
        t0 = datetime(2026, 11, 10, 9, tzinfo=KST)
        A.scan(t0, self.root, self.state, self.rows(6.2))
        A.scan(t0 + timedelta(days=2), self.root, self.state, self.rows(5.4, "20261112"))
        self.assertIsNone(A.alert_line("co-x", self.state))

    def test_hold_days_without_rescoring(self):
        t0 = datetime(2026, 11, 10, 9, tzinfo=KST)
        A.scan(t0, self.root, self.state, self.rows(6.2))
        self.assertEqual(A.scan(t0 + timedelta(days=A.HOLD_DAYS), self.root, self.state, self.rows(6.2)), (0, 1))

    def test_min_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = make_root(tmp, rep_date="2026-11-05")
            ev = A.evaluate("co-x", A.latest_reports(root)["co-x"], self.rows(7.0), datetime(2026, 11, 10).date(), root)
        self.assertFalse(ev["ok"])
        self.assertIn("14일", ev["why"])

    def test_cohort_drift_subtracted(self):
        rows = {f"c{i}": {"total": 6, "scored_on": "20261107", "delta": 1.1} for i in range(12)}
        rows["co-x"] = {"total": 6.2, "scored_on": "20261107", "delta": 1.2, "name": "X"}
        ev = A.evaluate("co-x", A.latest_reports(self.root)["co-x"], rows, datetime(2026, 11, 10).date(), self.root)
        self.assertFalse(ev["ok"])   # +1.2 − 쏠림 1.1 = +0.1

    def test_due_window_and_daily_cap(self):
        st = {"watch": {}, "queue": [{"id": "co-x", "status": "대기", "rise": 1.2, "registered": "2026-11-10T09:00:00+09:00"}], "done": []}
        A.save(st, self.state)
        self.assertEqual(A.due(datetime(2026, 11, 13, 13, tzinfo=KST), self.state)["items"], [])
        self.assertEqual(len(A.due(datetime(2026, 11, 13, 20, tzinfo=KST), self.state)["items"]), 1)
        st["done"] = [{"id": "co-y", "at": "2026-11-13T06:10:00+09:00"}]
        A.save(st, self.state)
        self.assertEqual(A.due(datetime(2026, 11, 13, 20, tzinfo=KST), self.state)["items"], [])

    def test_section_compares(self):
        x = {"report_date": "2026-10-20", "base_alpha": 5.0, "alpha": 6.2, "confirmed": "다음 산정 유지", "basis": "리포트 기록", "drift": 0}
        sec = A.section(x, {"verdict": {"alpha": 5.0, "rating": "Neutral"}}, {"verdict": {"alpha": 6.2, "rating": "Buy"}},
                        [("이전 판 보기", "https://claude.ai/artifact/a")])
        self.assertEqual(sec["h2"], "갱신 사유")
        self.assertIn(["구매등급", "Neutral", "Buy"], sec["blocks"][2]["rows"])
        self.assertIn("claude.ai/artifact/a", sec["blocks"][1]["text"])


class TestNotes(unittest.TestCase):
    def test_unread_without_body(self):
        item = {"item_id": "t:1", "title": "x", "url": "https://news.google.com/rss/articles/abc"}
        orig = item_notes._card_text
        item_notes._card_text = lambda _id: ""
        try:
            self.assertIn("본문 미확인", item_notes.note(item, "X", state={}))
        finally:
            item_notes._card_text = orig

    def test_model_line_and_alpha_fact(self):
        item = {"item_id": "t:2", "title": "x", "url": "", "published_at": "2026-11-12"}
        orig = item_notes.body_of
        item_notes.body_of = lambda it: ("본문 " * 200, "원문")
        try:
            out = item_notes.note(item, "X", {"total": 6.1, "delta": 1.2, "scored_on": "20261113"},
                                  caller=lambda p: {"summary": "투자자 행사 참석 공지일 뿐 실적 정보 없음", "alpha_relevant": False}, state={})
        finally:
            item_notes.body_of = orig
        self.assertEqual(out, "→ 투자자 행사 참석 공지일 뿐 실적 정보 없음 — 알파 변화 요인 아님 (알파 4.9→6.1)")


class TestCycleAndMos(unittest.TestCase):
    def test_mos_is_graham_discount(self):
        self.assertAlmostEqual(decision.mos_discount(2.23), 1 - 1 / 2.23)
        self.assertIn("안전마진 55%", decision.mos_text(2.23))
        self.assertIn("안전마진 없음", decision.mos_text(0.8))

    def test_memory_gets_cyclical_spec(self):
        self.assertEqual(plus.cyclical_spec({"id": "co-skhynix"})["peer"], "MU")
        self.assertIsNone(plus.cyclical_spec({"id": "co-nonexistent-x"}))
        self.assertEqual(plus.cyclical_spec({"id": "co-skhynix", "cyclical": {"normal": 0.3}}), {"normal": 0.3})

    def test_cyclical_sigma_wider(self):
        if plus.cycle_sigma("MU") is None:
            self.skipTest("MU 이력 없음")
        self.assertGreater(plus.margin_sigma({"id": "co-skhynix"}, 0.02), 0.1)
        self.assertEqual(plus.margin_sigma({"id": "co-nonexistent-x"}, 0.02), 0.02)


if __name__ == "__main__":
    unittest.main()
