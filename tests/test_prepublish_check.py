"""Analysis 발행 전 점검(마스터 지시 2026-11-22 "Analysis Report 초안에서 실수를 최소화하도록")"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import prepublish_check as P  # noqa: E402


def run(fn, *a):
    out = []
    fn(*a, lambda st, n, d: out.append((st, n)))
    return out


class Gate(unittest.TestCase):
    def test_customer_group(self):
        d = {"summary": [{"q": "누가 사 주나", "a": "최대 고객 중국 고객(집계) 29%, 상위 3곳 70%"}]}
        self.assertTrue(run(P.check_customers, d, {"customers": {"items": [{"name": "중국 고객(집계)"}]}}))
        self.assertFalse(run(P.check_customers, d, {"customers": {"items": [{"name": "Apple"}]}}))

    def test_tiles(self):
        d = {"verdict": {"target": 1.1, "view": "목표주가 $1.10"}, "tiles": [{"k": "업사이드", "v": "+10%", "sub": "목표주가 $1 · 손익비 0.0"}, {"k": "가이던스", "v": ""}]}
        names = run(P.check_tiles, d, {})
        self.assertEqual(len(names), 3)

    def test_backlog_and_prose(self):
        self.assertTrue(run(P.check_backlog, {"pipeline": {"reported_backlog": 4.5, "items": [{"status": "확정", "total": 4.5}, {"status": "확정", "total": 4.5}]}}))
        d = {"verdict": {"view": "매출 $1,250M"}, "sections": [{"blocks": [{"type": "table", "rows": [["$1,250M"]]}]}]}
        self.assertEqual(len(run(P.check_text, d, "")), 1)
        d2 = {"verdict": {"view": "EPS −131% 감소"}, "sections": []}
        self.assertFalse(run(P.check_text, d2, ""))

    def test_session(self):
        self.assertEqual(P.session_of("2026-08-12T11:05:00.000Z"), ("before", "2026-08-12"))
        self.assertEqual(P.session_of("2026-11-09T21:10:00.000Z"), ("after", "2026-11-09"))


if __name__ == "__main__":
    unittest.main()
