"""Ten-bagger Report 발행 알림 양식 (마스터 지시 2026-11-01)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import report_feed as rf  # noqa: E402

DOC = {"date": "2026-11-01", "ticker": "X", "company": "엑스", "title": "제목", "biz": "사업", "format": 3,
       "verdict": {"rating": "Neutral", "alpha": 6.2, "upside": 0.136, "downside": -0.34, "rr": 1.91, "points": [["좋은 점", "수요 확인"], ["나쁜 점", "재고 증가"]]},
       "tiles": [{"k": "주가", "v": "$84.65", "sub": "고점 대비 -50% · 1년 -19%"}, {"k": "멀티플", "v": "Fwd 1Y P/E 23.7배", "sub": "동종 중앙값 30.7배"}, {"k": "구매등급", "v": "Neutral", "sub": "애널리스트 9명"}],
       "gallery": [{"kind": "scenario", "cases": [{"name": "약세", "value": 55.5}, {"name": "기본", "value": 94.4}, {"name": "강세", "value": 140.4}]}],
       "sections": [{"h2": "밸류에이션", "blocks": [{"type": "hl", "text": "DCF 기준 업사이드는 기본 -50%, 강세 -30%"}, {"type": "table", "title": "멀티플 선정 — Fwd 1Y P/E", "rows": [["**선정**", "**23.9배**", "x"]]}]},
                    {"h2": "약세 논리 및 셀온 조건", "blocks": [{"type": "boxes", "items": [{"title": "셀온 조건", "lines": [["조건 1", "제품 매출 둔화."]]}]}]},
                    {"h2": "체크리스트", "blocks": [{"type": "table", "rows": [["11월 중순", "13F", "의미"]]}]}]}


class TestFeed(unittest.TestCase):
    def test_sections_in_reading_order(self):
        s = rf.build(DOC)
        order = [s.index(k) for k in ("■ 결론", "■ 왜 이렇게 보나", "■ 밸류에이션", "■ 셀온 조건", "■ 다음 확인")]
        self.assertEqual(order, sorted(order))
        self.assertIn("업사이드 +14% · 다운사이드 −34% · 손익비 1.9", s)
        self.assertIn("- 시나리오: 약세 $56 · 기본 $94 · 강세 $140", s)
        self.assertIn("- 멀티플: 지금 23.7배 · 선정 23.9배 · 동종 중앙값 30.7배", s)
        self.assertIn("- DCF 기준 업사이드 −50%", s)
        self.assertIn("- 좋은 점: 수요 확인", s)
        self.assertIn("- 11월 중순: 13F", s)
        self.assertIn(rf.ZACKS, s)

    def test_view_sentences_when_no_points(self):
        d = {**DOC, "verdict": {**DOC["verdict"], "points": None, "view": "**수요는 확인됐다.** 값은 비싸다. 램프가 가른다. 네 번째다."}}
        rows = rf.reasons(d)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][1], "수요는 확인됐다.")

    def test_no_zacks_line_without_coverage(self):
        d = {**DOC, "tiles": DOC["tiles"][:2] + [{"k": "구매등급", "v": "Neutral", "sub": "애널리스트 등급 미확인"}]}
        self.assertNotIn(rf.ZACKS, rf.build(d))


if __name__ == "__main__":
    unittest.main()
