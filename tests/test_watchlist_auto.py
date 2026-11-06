"""Portfolio 와치리스트 자동 편입·제외 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "portfolio"))
import watchlist as w  # noqa: E402

C = {"add": {"alpha_min": 6.0, "composite_pct": 0.75, "buy_call_counts": True, "confirm_days": 2},
     "remove": {"alpha_pct": 0.5, "composite_pct": 0.5, "confirm_days": 3, "killed_immediate": True},
     "cap": {"max_auto": 1, "replace_margin": 1.0}}


def mt():
    m = {f"x{i}": {"ticker": f"X{i}", "alpha": 3.0 + i * 0.5, "composite": 3.0 + i * 0.4, "adv_ok": True} for i in range(8)}
    m["held"] = {"ticker": "H", "alpha": 9, "composite": 9, "adv_ok": True}
    return m


class T(unittest.TestCase):
    def test_add_needs_two_days_and_skips_held(self):
        H = [{"id": "held", "status": "보유"}]
        st = {}
        self.assertEqual(w.decide(H, mt(), C, st, "2026-11-04"), ([], []))
        adds, _ = w.decide(H, mt(), C, st, "2026-11-05")
        self.assertEqual(adds, ["x7"])   # 상한 1 — 종합 최고만, 보유는 후보 아님

    def test_remove_needs_both_low_three_days(self):
        H = [{"id": "x0", "status": "관심"}, {"id": "x7", "status": "관심"}]
        st = {}
        for d in ("2026-11-04", "2026-11-05"):
            self.assertEqual(w.decide(H, mt(), C, st, d)[1], [])
        drops = w.decide(H, mt(), C, st, "2026-11-06")[1]
        self.assertEqual([i for i, _ in drops], ["x0"])

    def test_remove_when_add_criteria_unmet(self):
        H = [{"id": "x5", "status": "관심"}]   # 알파 5.5 < 6.0 — 중앙값 위여도 편입 기준 미달이면 제외(2026-11-06)
        st = {}
        for d in ("2026-11-04", "2026-11-05"):
            w.decide(H, mt(), C, st, d)
        self.assertEqual([i for i, _ in w.decide(H, mt(), C, st, "2026-11-06")[1]], ["x5"])

    def test_low_alpha_removed_without_composite_and_pin_kept(self):
        m = mt(); m["nc"] = {"ticker": "NC", "alpha": 4.0}; m["pp"] = {"ticker": "PP", "alpha": 1.0}
        H = [{"id": "nc", "status": "관심"}, {"id": "pp", "status": "관심", "pin": True}]
        st = {}
        for d in ("2026-11-04", "2026-11-05"):
            w.decide(H, m, C, st, d)
        self.assertEqual([i for i, _ in w.decide(H, m, C, st, "2026-11-06")[1]], ["nc"])

    def test_unknown_metrics_never_remove(self):
        H = [{"id": "ghost", "status": "관심"}]
        st = {}
        for d in ("2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07"):
            self.assertEqual(w.decide(H, mt(), C, st, d)[1], [])

    def test_apply_marks_ended_not_deleted(self):
        text = "holdings:\n  - id: a\n    ticker: A\n    status: 관심\n\nevents:\n  - {}\n"
        out = w.apply(text, ["b"], [("a", "이유")], {"b": {"ticker": "B", "name": "Bee", "alpha": 7, "composite": 6}}, "2026-11-04")
        self.assertIn("status: 종료", out)
        self.assertIn("id: a", out)
        self.assertIn("  - id: b\n", out)
        self.assertLess(out.index("id: b"), out.index("events:"))


if __name__ == "__main__":
    unittest.main()
