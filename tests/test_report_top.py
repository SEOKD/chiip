"""텐배거 리포트 상단 구성 시험 (마스터 지시 2026-10-29 — 컨빅션·알파·업사이드, 약어 풀어 쓰기, 그래프 전체를 상단에)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))

import report_html  # noqa: E402

D = {"title": "t", "date": "2026-10-29", "ticker": "TST", "company": "Test", "biz": "b",
     "verdict": {"view": "v2 기본 0.44배·MC P50 0.5배", "confidence": "중", "insight": 7},
     "summary": [{"q": "q", "a": "a"}],
     "sections": [{"h2": "주가", "blocks": [{"type": "chart", "chart": {"kind": "line", "title": "주가(달러)", "series": [{"name": "s", "points": [["2026-01", 1], ["2026-02", 2]]}]}}]},
                  {"h2": "시나리오", "blocks": [{"type": "p", "text": "본문"},
                                             {"type": "chart", "chart": {"kind": "scenario", "title": "2027년 말 주가", "current": 100,
                                                                         "cases": [{"name": "약세", "value": 50, "prob": 0.3}, {"name": "기본", "value": 120, "prob": 0.5}, {"name": "강세", "value": 200, "prob": 0.2}]}}]}],
     "sources": ["a"]}


class TestReportTop(unittest.TestCase):
    def test_badges_and_upside(self):
        h = report_html.render(D)
        self.assertIn("컨빅션 중", h)
        self.assertIn("알파 7/10", h)
        self.assertIn("업사이드 +15%", h)          # (0.3×50 + 0.5×120 + 0.2×200)/100 − 1 = +15%
        self.assertNotIn("확신도", h)
        self.assertNotIn("인사이트 7", h)

    def test_plain_words(self):
        h = report_html.render(D)
        self.assertNotIn("v2", h)
        self.assertIn("내재가치(기본)", h)
        self.assertIn("중앙값", h)

    def test_gallery_first_and_once(self):
        h = report_html.render(D)
        g, s = h.find("한눈에 보기"), h.find("<h2>주가</h2>")
        self.assertTrue(0 < h.find("한 장 요약") < g < s)   # Chiip View → 한 장 요약 → 그래프 전체 → 본문
        self.assertEqual(h.count("<svg"), 2)                 # 그래프는 상단에 한 번씩만, 본문은 링크
        self.assertIn('href="#fig2"', h)


if __name__ == "__main__":
    unittest.main()
