"""노션 텔레그램 문안 다듬기(마스터 지시 2026-11-08 — 노션 피드 가독성)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import notion_watch as NW  # noqa: E402


class TestTidy(unittest.TestCase):
    def test_layout(self):
        raw = ("[노션 IB] 노무라 — 지연·비용 상승 (1차 판정, 미검증)\n결론: 취소가 아니라 지연이다.\n- 지연 노출 약 7%(노무라 추정)\n"
               "반대 근거: 공약은 시행이 아니다.\n다음 확인: 텍사스 허가 중단 문서\n상세: outputs/report/notion/x.md\n공개 자료 기반 분석이며 투자 권유가 아님")
        out = NW.tidy(raw)
        self.assertTrue(out.startswith("[Chiip Notion · IB] 노무라 — 지연·비용 상승\n"))
        self.assertNotIn("outputs/", out)
        self.assertIn("• 지연 노출", out)
        self.assertIn("\n\n반대 근거:", out)
        self.assertTrue(out.endswith("1차 판정·미검증 · 공개 자료 기반 분석이며 투자 권유가 아님"))
        self.assertEqual(out.count("1차 판정"), 1)


if __name__ == "__main__":
    unittest.main()
