"""텐배거 일일 리포트 렌더러·선정기 시험 — 2026-10-29"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))

import pick_report  # noqa: E402
import report_html  # noqa: E402


class TestRender(unittest.TestCase):
    def base(self):
        return {"title": "T", "date": "2026-10-29", "ticker": "X", "company": "Co", "biz": "사업",
                "verdict": {"view": "판단 **굵게**", "confidence": "중", "insight": 7},
                "sections": [{"h2": "차트", "blocks": [
                    {"type": "chart", "chart": {"kind": "line", "title": "L", "series": [{"name": "s", "points": [["2026-01", 1], ["2026-02", 3]]}]}},
                    {"type": "chart", "chart": {"kind": "bars", "title": "B", "categories": ["a", "b"], "series": [{"name": "s", "values": [1, None]}]}},
                    {"type": "chart", "chart": {"kind": "hbars", "title": "H", "rows": [{"label": "r", "bars": [{"name": "x", "value": 2}]}]}},
                    {"type": "chart", "chart": {"kind": "scenario", "title": "S", "current": 100, "cases": [
                        {"name": "약세", "value": 50, "prob": 0.5}, {"name": "강세", "value": 300, "prob": 0.5}]}}]}]}

    def test_render_all_charts_and_escape(self):
        d = self.base()
        d["summary"] = [{"q": "<script>alert(1)</script>", "a": "ok"}]
        h = report_html.render(d)
        self.assertEqual(h.count("<svg"), 4)
        self.assertNotIn("<script>alert", h)                 # 수집 문장 속 스크립트는 이스케이프
        self.assertIn("<b>굵게</b>", h)
        self.assertIn("확률 가중 175", h)                     # 0.5×50 + 0.5×300
        self.assertIn("투자 권유가 아님", h)
        self.assertNotIn("NaN", h)

    def test_required_fields(self):
        d = self.base()
        del d["biz"]
        with self.assertRaises(ValueError):
            report_html.render(d)


class TestPick(unittest.TestCase):
    def test_queue_first_then_skip_recent(self):
        with tempfile.TemporaryDirectory() as tmp:
            q, log = Path(tmp) / "q.txt", Path(tmp) / "log.csv"
            q.write_text("CBRS\n", encoding="utf-8")
            with mock.patch.object(pick_report, "QUEUE", q), mock.patch.object(pick_report, "LOG", log):
                p = pick_report.pick(date(2026, 10, 29))
                self.assertEqual(p["reason"], "마스터 요청 대기열")
                pick_report.done(p["id"], "CBRS", "x.html", "v", date(2026, 10, 29))
                self.assertEqual(q.read_text(encoding="utf-8"), "")
                self.assertNotEqual(pick_report.pick(date(2026, 10, 30)).get("ticker"), "CBRS")   # 30일 안 재작성 금지


if __name__ == "__main__":
    unittest.main()
