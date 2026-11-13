"""커뮤니티 반응 풀이(마스터 지시 2026-11-13) — 통계 한 줄 + 논지 3~5개(출처·날짜·사실 확인 표시)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import social_view as sv  # noqa: E402

V = {"side": "강세", "claim": "회비 인상에도 방문이 늘었다는 점을 든다", "basis": "3Q 콜", "source": "Seeking Alpha", "date": "2026-10-30", "check": "확인"}


class TestViews(unittest.TestCase):
    def test_stat_line_first_then_views_with_source_and_flag(self):
        sec = sv.section({"social": {"summary": "s", "views": [V, {**V, "side": "약세", "claim": "회원이 줄었다", "check": "사실관계 미확인", "source": "레딧 r/stocks"}]}}, "x-none")
        texts = [b.get("text", "") for b in sec["blocks"]]
        self.assertTrue(texts[0].startswith("통계:"))
        self.assertTrue(any("(Seeking Alpha, 2026-10-30)" in t for t in texts))
        self.assertTrue(any("[사실관계 미확인]" in t for t in texts))
        self.assertEqual(sec["h2"], "커뮤니티 반응")

    def test_few_mentions_not_invented(self):
        sec = sv.section({"social": {"views": [], "few": True}}, "x-none")
        self.assertTrue(any("언급 적음" in b.get("text", "") for b in sec["blocks"]))

    def test_rejects_long_quote_and_missing_date(self):
        with self.assertRaises(ValueError):
            sv.section({"social": {"views": [{**V, "quote": " ".join(["w"] * 16)}]}}, "x")
        with self.assertRaises(ValueError):
            sv.section({"social": {"views": [{**V, "date": ""}]}}, "x")


if __name__ == "__main__":
    unittest.main()
