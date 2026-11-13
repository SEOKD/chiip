"""Pulse 텔레그램 양식 (마스터 지시 2026-11-02)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))

import notify  # noqa: E402
import pulse_check  # noqa: E402
import pulse_feed  # noqa: E402

ITEM = {"icon": "⚡", "name": "Alphabet", "code": "GOOGL", "event": "3Q 보통주 $12.4B 분할 매도", "biz": "구글 검색·유튜브·클라우드 지주회사",
        "view": "AI 설비투자 자금줄이 자본시장으로 옮겨가는 중", "insight": 7, "conviction": 8, "basis": "1차 서류",
        "why": ["1~3Q 외부 조달 $147B", "실적 후 +1.3%, 희석에 둔감"], "against": "기회주의 발행일 수도 → 10-Q 월별 내역이 가른다",
        "next": "3Q 10-Q(11월 초)", "links": [["8-K 원문", "https://www.sec.gov/x"], ["보도", "https://b.example/y"]]}
LOW = dict(ITEM, name="Meta", code="META", insight=4, conviction=4)


class TestBuild(unittest.TestCase):
    def text(self, **kw):
        return pulse_feed.build({"time": "16:24", "items": [LOW, ITEM], **kw})

    def test_order_follows_report_feed(self):
        t = self.text()
        heads = [t.index(x) for x in ("**■ 결론**", "**■ 근거**", "**■ 반대**", "**■ 다음 확인**", "[8-K 원문]")]
        self.assertEqual(heads, sorted(heads))

    def test_highest_insight_first(self):
        t = self.text()
        self.assertLess(t.index("① Alphabet"), t.index("② Meta"))

    def test_passes_format_check(self):
        self.assertEqual(pulse_check.check(self.text()), [])
        self.assertEqual(pulse_check.unlinked(self.text()), [])

    def test_missing_link_is_stopped(self):
        t = pulse_feed.build({"time": "16:24", "items": [dict(ITEM, links=[])]})
        self.assertIn("출처 미확인", t)

    def test_long_evidence_is_measured(self):
        t = pulse_feed.build({"time": "16:24", "items": [dict(ITEM, why=["가" * 60])]})
        self.assertEqual([r[0] for r in pulse_check.check(t)], ["evidence"])

    def test_at_most_three_reasons(self):
        t = pulse_feed.build({"time": "16:24", "items": [dict(ITEM, why=["가", "나", "다", "라"])]})
        self.assertNotIn("· 라", t)

    def test_brief_is_one_line_each(self):
        t = pulse_feed.build({"time": "16:24", "items": [], "brief": [{"name": "삼성전기", "code": "009150", "line": "판가 증거는 아직 없음", "link": ["보도", "https://x.example/a"]}],
                              "empty": ["숏 리포트"]})
        self.assertIn("· 삼성전기 009150 — 판가 증거는 아직 없음 [보도](https://x.example/a)", t)
        self.assertNotIn("그 외 새 건 없음", t)   # 2026-11-13 마스터 지시 — Pulse 끝 두 줄 삭제
        self.assertNotIn("투자 권유가 아님", t)

    def test_readable_keeps_section_with_its_list(self):
        self.assertIn("**■ 근거**\n· 1~3Q", notify.readable(self.text()))


if __name__ == "__main__":
    unittest.main()
