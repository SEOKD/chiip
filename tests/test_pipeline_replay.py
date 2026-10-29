"""즉시 포착 회귀 시험 — 2026-10-29 실제로 놓친 사건을 제목 그대로 다시 돌린다(마스터 지시 "CBRS 숏 리포트나 Marvell의
Lumentum 인수 기사 같은 걸 즉시 찾아오는 파이프라인" 점검). 규칙이 바뀌어 이 사건들을 다시 놓치면 실패한다."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))

from pollers import common  # noqa: E402
from pollers import short_sites  # noqa: E402
import notify  # noqa: E402
import promote  # noqa: E402


def judge(title, publisher, source_id):
    it = {"title": title, "publisher": publisher, "source_id": source_id, "entities_matched": common.match_entities(title)}
    hit = promote.match(it)
    return promote.level_for(it, hit[0]) if hit else None


class TestMissedEvents(unittest.TestCase):
    def test_marvell_lumentum(self):
        for title, pub, src in [("Marvell Is Said to Near Megadeal for Lumentum in AI Push", "Bloomberg", "src-bbg-direct"),
                                ("Marvell in Talks to Buy Lumentum - The Information", "The Information", "src-news7-focus"),
                                ("Marvell in advanced talks to buy Lumentum, Bloomberg News reports - Reuters", "Reuters", "src-news7-focus")]:
            self.assertEqual(judge(title, pub, src), "P0", title)

    def test_culper_cerebras_variants(self):
        """실제 숏 리포트 제목은 'short'를 쓰지 않는 경우가 많다 — 운용사 이름(짧은 이름 포함) + 대상 종목이면 잡는다"""
        for title, pub, src in [("Cerebras Systems (CBRS): Hot Garbage", "Culper Research", "src-short-sites"),
                                ("Culper Research vs Cerebras: A Neutral Engineering-Driven View", "Irrational Analysis", "src-research-feeds"),
                                ("Culper Research Takes Aim at Cerebras", "Benzinga", "src-gnews"),
                                ("Cerebras shares fall after Culper report", "Reuters", "src-news7-focus"),
                                ("Cerebras stock sinks after short seller alleges overstated demand", "Reuters", "src-news7-focus")]:
            self.assertEqual(judge(title, pub, src), "P0", title)

    def test_short_site_non_holding(self):
        self.assertEqual(judge("Coherent (NYSE: COHR): The AI Optics Darling Is A House Of Cards", "Grizzly Research", "src-short-sites"), "P1")

    def test_no_false_positive(self):
        self.assertIsNone(judge("Muddy Waters founder Carson Block on markets podcast", "CNBC", "src-news7-focus"))
        self.assertIsNone(judge("International Games System — Profits", "Grizzly Research", "src-short-sites"))   # 대상 불명


class TestShortSitesParser(unittest.TestCase):
    def test_page_links(self):
        html = ('<a href="/about">About Us</a><a href="https://x.com/r/cerebras-hot-garbage">Cerebras (CBRS): Hot Garbage</a>'
                '<a href="https://other.com/a">Some Other Site Article Here</a><a href="/r/2">Read more</a>')
        links = short_sites.page_links(html, "https://www.x.com")
        self.assertEqual(links, {"https://x.com/r/cerebras-hot-garbage": "Cerebras (CBRS): Hot Garbage"})


class TestTelegramFormat(unittest.TestCase):
    def test_md_and_codes(self):
        self.assertEqual(notify.md_to_html("**판단** a<b\n[원문](https://s.gov/a?x=1&y=2)"),
                         '<b>판단</b> a&lt;b\n<a href="https://s.gov/a?x=1&amp;y=2">원문</a>')
        self.assertEqual(notify.brand("[치입 펄스 16:24]\n본문\n보강 적용: D-20261029-02\n끝"), "[Chiip 펄스 16:24]\n본문\n끝")
        self.assertEqual(notify.brand("[치입 포트폴리오 P0 · 늦은 보고]"), "[Chiip 포트폴리오 늦은 보고]")


if __name__ == "__main__":
    unittest.main()
