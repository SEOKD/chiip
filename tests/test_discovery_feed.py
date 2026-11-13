"""Discovery 피드 양식 (마스터 지시 2026-11-01)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
import feed  # noqa: E402

DOC = {"date": "11/01", "summary": ["신규 편입 없음"],
       "deep": [{"name": "National Presto(NPK)", "theme": "탄약", "stage": "보류", "biz": "방위 탄약 회사", "view": "10배 경로 증거 없음", "points": [["증거", "방위 매출 +25%"], ["다음", ""]]}],
       "top": [{"name": "MilDef", "score": 6.8, "stage": "아이디어"}]}


class TestFeed(unittest.TestCase):
    def setUp(self):   # 양식 시험 — 알파 5점 관문(실제 알파 점수에 따라 바뀐다)은 따로 본다(2026-11-14 점검: 표본 이름이 관문에 걸려 깨지던 문제)
        self._gate = feed.gate
        feed.gate = lambda d: dict(d)

    def tearDown(self):
        feed.gate = self._gate

    def test_conclusion_comes_first_with_blank_lines(self):
        s = feed.render(DOC)
        self.assertLess(s.index("이번 회차 결론"), s.index("심층 검토"))
        self.assertLess(s.index("심층 검토"), s.index("선별 상위"))
        self.assertIn("\n\n**■ 선별 상위**\n- MilDef 6.8 · 아이디어", s)
        self.assertIn("- 판단: 10배 경로 증거 없음", s)
        self.assertNotIn("- 다음", s)
        self.assertTrue(s.endswith(feed.FOOT))

    def test_empty_sections_disappear(self):
        s = feed.render({"date": "11/01", "summary": ["없음"]})
        self.assertNotIn("소비재", s)
        self.assertNotIn("시가총액", s)

    def test_long_lines_are_rejected(self):
        self.assertEqual(feed.check(DOC), [])
        self.assertTrue(feed.check({"summary": ["가" * 41]}))
        self.assertTrue(feed.check({"deep": [{"view": "가" * 71}]}))


if __name__ == "__main__":
    unittest.main()
