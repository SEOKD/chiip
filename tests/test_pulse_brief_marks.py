"""Pulse '간단히' 해설 단락마다 ■ (마스터 지시 2026-11-18)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import pulse_feed  # noqa: E402

SRC = """[Chiip Pulse 02:15]

**■ 간단히**
· 엔비디아 NVDA
기업: AI 가속기
FT 보도: 싱가포르 매출

**판단:** 기준 변경

■반증: 10-Q

원문: [marketfeed](https://t.me/marketfeed/1)

그 외 새 건 없음: 숏 리포트

1차 판정, 미검증 · 공개 자료 기반 분석이며 투자 권유가 아님"""


class TestBriefMarks(unittest.TestCase):
    def test_paragraphs_marked(self):
        out = pulse_feed.brief_marks(SRC)
        for s in ("· 엔비디아 NVDA\n\n■ 기업: AI 가속기", "\n\n■ FT 보도", "\n\n■ **판단:**", "\n\n■ 반증: 10-Q", "\n\n■ 원문:"):
            self.assertIn(s, out)
        self.assertNotIn("그 외 새 건 없음", out)
        self.assertIn("\n1차 판정, 미검증", out)
        self.assertNotIn("■ 1차 판정", out)

    def test_one_line_briefs_unchanged(self):
        s = "[Chiip Pulse 09:00]\n\n**■ 간단히**\n· A AAA — 한 줄\n· B BBB — 둘째 줄"
        self.assertEqual(pulse_feed.brief_marks(s), s)

    def test_judgment_items_untouched(self):
        s = "[Chiip Pulse 09:00]\n\n**⚡ ① A AAA｜사건**\n기업: 사업\n\n**■ 결론**\n**판단**"
        self.assertEqual(pulse_feed.brief_marks(s), s)


if __name__ == "__main__":
    unittest.main()
