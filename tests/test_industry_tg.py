"""Industry Report 텔레그램 피드 양식 (마스터 지시 2026-11-08)"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "industry"))
import tg_feed as tg  # noqa: E402

D = {"kind": "industry_event", "date": "2026-11-08", "title": "제목", "event": "사건 설명",
     "ratings": [{"name": "A", "rating": "Attractive"}, {"name": "B", "rating": "In-Line"}, {"name": "C", "rating": "In-Line"}],
     "summary": [{"q": "민주당도 돈을 받았나?", "a": "그렇다. 데이터센터·AI 4개사 PAC 기부의 46%가 민주 후보에게 갔다(FEC 상위 기부). 두 번째 문장은 길어서 빠진다."}],
     "tiles": [{"k": "파이프라인", "v": "173GW", "sub": "전체의 50% (dcmap)"}],
     "sections": [{"h2": "⑧ 반증", "blocks": [{"type": "table", "headers": ["기한", "무엇", "잴 것", "확률", "맞으면"],
                                               "rows": [["2027-04-30", "주지사 행정 조치(행정명령·지시)를 발표한다", "공식 발표", "75%", "지지"],
                                                        ["2027-01-20", "4분기 로비가 3분기 이상이다", "LD-2", "60%", "지지"]]}]}]}


class TestIndustryTg(unittest.TestCase):
    def test_layout(self):
        t = tg.build(D, "https://a", "https://n")
        self.assertTrue(t.startswith("[Chiip Industry Report · 사건 때 심층 · 11/08]"))
        self.assertIn("🟢 **Attractive** — A", t)
        self.assertIn("⚪ **In-Line** — B, C", t)
        self.assertIn("그렇다. 데이터센터·AI 4개사 PAC 기부의 46%가 민주 후보에게 갔다.", t)   # 짧은 첫 문장은 잇고 괄호는 뺀다
        self.assertNotIn("두 번째 문장", t)
        self.assertIn("• 173GW — 파이프라인(전체의 50%)", t)
        self.assertLess(t.index("01/20"), t.index("04/30"))   # 날짜 순
        self.assertNotIn("(행정명령", t)
        self.assertEqual(tg.check(t), [])
        self.assertTrue(t.rstrip().endswith(tg.DISCLAIMER))


if __name__ == "__main__":
    unittest.main()
