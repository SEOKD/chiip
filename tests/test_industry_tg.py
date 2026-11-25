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
    def test_concise(self):   # 2026-11-25 마스터 지시 '간결하게'
        d = dict(D, kind="industry", cycle="quarterly", title="후공정 결산 — 첨단 패키징 +51%",
                 ratings=[{"name": "ASE 사업부(다음 분기 = 10~12월)", "rating": "In-Line"}],
                 tiles=[{"k": "매출(전분기)", "v": "+15.9%", "sub": "$6.6B · 2사"}, {"k": "매출(전년)", "v": "+35.8%", "sub": "2사 기준"}])
        t = tg.build(d)
        self.assertIn("**후공정 결산**" + chr(10) + chr(10) + "📌 첨단 패키징 +51%.", t)
        self.assertIn("⚪ **In-Line**(중립) — ASE 사업부", t)
        self.assertNotIn("사건:", t)
        self.assertIn("📊 매출 +15.9% 전분기 · +35.8% 전년 ($6.6B)", t)

    def test_layout(self):
        t = tg.build(D, "https://a", "https://n")
        self.assertTrue(t.startswith("[Chiip Industry · 사건 때 심층 · 11/08]"))
        self.assertIn("🟢 **Attractive**(유리) — A", t)
        self.assertIn("⚪ **In-Line**(중립) — B, C", t)
        self.assertIn("▸ 민주당도 돈을 받았나?" + chr(10) + "   ↳ 그렇다. 데이터센터·AI 4개사 PAC 기부의 46%가 민주 후보에게 갔다", t)   # 짧은 첫 문장은 다음 문장 첫 절까지, 괄호는 뺀다
        self.assertNotIn("두 번째 문장", t)
        self.assertIn("📊 파이프라인 173GW (전체의 50%)", t)
        self.assertLess(t.index("01/20"), t.index("04/30"))   # 날짜 순
        self.assertNotIn("(행정명령", t)
        self.assertEqual(tg.check(t), [])
        self.assertTrue(t.rstrip().endswith(tg.DISCLAIMER))


if __name__ == "__main__":
    unittest.main()
