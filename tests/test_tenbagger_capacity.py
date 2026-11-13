"""Ten-bagger 역량 보강 시험 (2026-11-14 점검, ADR-037) — 펀더멘털 일괄 채우기·판단 카드 edge 반영·카드 대기열"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
import fund_fill as ff  # noqa: E402
import screen  # noqa: E402


class FundFill(unittest.TestCase):
    def test_code_wraps_template_once_per_key(self):
        js = ff.code(3)
        self.assertTrue(js.startswith("async () => {"))
        self.assertIn("const one = async k => {", js)
        self.assertNotIn('const k = "__KEY__"', js)
        self.assertNotIn("console.log(JSON.stringify({\n    key", js)        # 템플릿의 출력 줄은 return으로 바뀐다
        self.assertIn("i += 1", js)                                         # 샌드박스 동시 호출 6개 = 종목 하나씩
        self.assertEqual(js.count("console.log("), 1)

    def test_priority_order(self):
        alpha = {"b": {"total": 6.0}}
        rows = [{"id": "d"}, {"id": "c", "rotation": True}, {"id": "b"}, {"id": "a", "edge": 7}]
        got = [r["id"] for r in sorted(rows, key=lambda r: ff.priority(r, alpha, {}))]
        self.assertEqual(got, ["a", "b", "c", "d"])

    def test_failed_ids_wait_a_week(self):
        with tempfile.TemporaryDirectory() as d:
            old = ff.TRIED, ff.candidates, ff.FUND
            ff.TRIED, ff.FUND = Path(d) / "t.json", Path(d) / "f.json"
            ff.candidates = lambda: [{"id": "us-x", "code": "X", "market": "us", "symbol": "NYSE:X"}]
            try:
                self.assertEqual(ff.todo(5, date(2026, 11, 14))[0], [("us-x", "NYSE_X")])
                ff.TRIED.write_text(json.dumps({"us-x": "2026-11-13"}), encoding="utf-8")
                self.assertEqual(ff.todo(5, date(2026, 11, 14))[0], [])
                self.assertEqual(ff.todo(5, date(2026, 11, 25))[0], [("us-x", "NYSE_X")])
            finally:
                ff.TRIED, ff.candidates, ff.FUND = old


class Cards(unittest.TestCase):
    def test_card_queue(self):
        rows = [{"id": "a", "stage": "① 아이디어", "comp": {"edge": 5}, "score": 6.5, "missing": []},
                {"id": "b", "stage": "① 아이디어", "comp": {"edge": 5}, "score": 6.0, "missing": ["growth"]},
                {"id": "c", "stage": "① 아이디어", "comp": {"edge": 7}, "score": 6.0, "missing": []},
                {"id": "d", "stage": "① 아이디어", "comp": {"edge": 5}, "score": 4.0, "missing": []}]
        old = screen._cards
        screen._cards = lambda: {}
        try:
            self.assertEqual([r["id"] for r in screen.card_queue(rows)], ["a"])
        finally:
            screen._cards = old

    def test_bottleneck_lens_exists_with_seven_questions(self):
        import re
        t = (ROOT / "knowledge" / "methods" / "sector_lenses" / "bottleneck.md").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"(?m)^\d+\. ", t)), 7)


if __name__ == "__main__":
    unittest.main()
