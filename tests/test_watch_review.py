"""관심 종목 편입 기준·유지 심사 시험 (마스터 결정 2026-11-13, ADR-024)"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "portfolio"))
import watch_review as wr  # noqa: E402

C = {"entry": {"alpha_min": 7.0, "research_days": 90, "mcap_min_b": 1.0, "adv_min_m": 10.0, "earnings_days": 120, "kill_required": True},
     "review": {"confirm_weeks": 2, "alpha_floor": 7.0, "alpha_drop": 1.0, "stale_days": 30, "entry_recheck": True}}
D = date(2026, 11, 13)


def f(**kw):
    base = {"id": "x", "ticker": "X", "name": "X", "pin": False, "added_by": None, "alpha": 7.5, "alpha_on": "20261110", "alpha_floor": None,
            "report": "2026-11-01", "drivers": True, "mcap_b": 5.0, "adv_m": 50.0, "earnings": "2026-10-25", "kill_written": True, "killed": False,
            "last_info": "2026-11-10"}
    return {**base, **kw}


class Entry(unittest.TestCase):
    def test_all_pass(self):
        self.assertTrue(wr.entry_ok(f(), C, D))

    def test_each_criterion_blocks(self):
        for kw in ({"alpha": 6.9}, {"report": "2026-07-01", "drivers": False}, {"mcap_b": 0.9}, {"adv_m": 5.0},
                   {"earnings": "2026-06-01"}, {"kill_written": False}):
            self.assertFalse(wr.entry_ok(f(**kw), C, D), kw)

    def test_unknown_blocks_entry(self):
        for kw in ({"alpha": None}, {"mcap_b": None}, {"adv_m": None}, {"earnings": None}):
            self.assertFalse(wr.entry_ok(f(**kw), C, D), kw)


class Review(unittest.TestCase):
    def setUp(self):
        self._facts = wr.facts
        self.cur = {}
        wr.facts = lambda h, today, ctx: self.cur[h["id"]]

    def tearDown(self):
        wr.facts = self._facts

    def run_(self, st, day, **kw):
        self.cur = {"x": f(**kw)}
        rows, st = wr.review([{"id": "x", "ticker": "X", "status": "관심"}, {"id": "h", "ticker": "H", "status": "보유"}], {}, C, st, day)
        return rows, st

    def test_held_not_reviewed(self):
        rows, _ = self.run_({}, D)
        self.assertEqual([r["id"] for r in rows], ["x"])

    def test_two_weeks_warning_makes_candidate_and_same_week_rerun_does_not_count(self):
        rows, st = self.run_({}, D, alpha=6.0)
        self.assertEqual(rows[0]["verdict"], "경고")
        rows, st = self.run_(st, date(2026, 11, 14), alpha=6.0)          # 같은 주
        self.assertEqual((rows[0]["verdict"], rows[0]["streak"]), ("경고", 1))
        rows, st = self.run_(st, date(2026, 11, 20), alpha=6.0)
        self.assertEqual(rows[0]["verdict"], "제외 후보")

    def test_warning_resets_when_clean(self):
        _, st = self.run_({}, D, alpha=6.0)
        rows, st = self.run_(st, date(2026, 11, 20))
        self.assertEqual((rows[0]["verdict"], rows[0]["streak"]), ("통과", 0))

    def test_alpha_drop_vs_previous_week(self):
        _, st = self.run_({}, D, alpha=9.0)
        rows, _ = self.run_(st, date(2026, 11, 20), alpha=8.0)
        self.assertTrue(any("직전 심사" in w for w in rows[0]["warnings"]), rows[0]["warnings"])

    def test_kill_and_stale_warn(self):
        rows, _ = self.run_({}, D, killed=True)
        self.assertTrue(any("테제 훼손" in w for w in rows[0]["warnings"]))
        rows, _ = self.run_({}, D, last_info="2026-09-01")
        self.assertTrue(any("장기 무변화" in w for w in rows[0]["warnings"]))

    def test_unknown_is_memo_not_warning(self):
        rows, _ = self.run_({}, D, mcap_b=None, adv_m=None)
        self.assertEqual(rows[0]["verdict"], "통과")
        self.assertIn("시총 미확인", rows[0]["memo"])

    def test_sweep_floor(self):
        rows, _ = self.run_({}, D, alpha=6.5, alpha_floor=6.0)
        self.assertEqual(rows[0]["verdict"], "통과")


class Output(unittest.TestCase):
    def test_daily_only_on_change(self):
        out = {"rows": [{"ticker": "X", "warnings": ["알파 6.0 < 7.0"]}], "changes": [], "proposals": []}
        self.assertEqual(wr.daily(out), "")
        out["changes"] = [{"ticker": "X", "from": "경고", "to": "제외 후보"}]
        s = wr.daily(out)
        self.assertIn("제외 후보", s)
        self.assertIn("승인", s)

    def test_apply_marks_ended_not_deleted(self):
        text = "holdings:\n  - id: a\n    ticker: A\n    status: 관심\n  - id: b\n    ticker: B\n    status: 보유\nevents:\n"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "p.yaml"
            p.write_text(text, encoding="utf-8")
            self.assertEqual(wr.apply(["a", "b"], "2026-11-20", port=p), ["a"])      # 보유는 건드리지 않는다
            t = p.read_text(encoding="utf-8")
            self.assertIn("status: 종료", t)
            self.assertIn("id: a", t)
            self.assertIn("status: 보유", t)


if __name__ == "__main__":
    unittest.main()
