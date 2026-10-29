"""규칙 상향(radar/promote.py)·P2 요약(radar/p2_digest.py)·펄스 파이낸싱 분류 오프라인 시험 — 마스터 지시 2026-10-29"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))

import p2_digest  # noqa: E402
import promote  # noqa: E402
import pulse  # noqa: E402

KST = timezone(timedelta(hours=9))


def item(title, ents=("co-broadcom",), pub=None, doc="기사", sid="src-news7-focus"):
    return {"title": title, "entities_matched": list(ents), "publisher": pub, "doc_type": doc, "source_id": sid, "snippet": ""}


class TestPromote(unittest.TestCase):
    def test_misses_of_20261029_now_promoted(self):
        self.assertIn("대형 거래", promote.match(item("Wall Street banks, Blackstone line up $63 billion to finance Broadcom AI chips for Anthropic - Reuters", pub="Reuters"))[0])
        self.assertIn("WSJ 단독", promote.match(item("Exclusive | Broadcom CEO Intervened to Seal Debt Deal - WSJ", pub="WSJ"))[0])
        self.assertIn("프런티어", promote.match(item("Anthropic Files for IPO to Become First Frontier AI Lab to List - Bloomberg", ents=()))[0])
        self.assertIn("보유 MRVL", promote.match(item("Broadcom wins custom chip order from OpenAI - Reuters", ents=()))[0])

    def test_financing_and_ma_promoted(self):
        self.assertIn("AI 자금 조달($3B)", promote.match(item("Nvidia to Invest $3 Billion in Meta’s Equity Offering as They Expand AI Partnership - WSJ", ents=(), pub="WSJ"))[0])
        self.assertIn("M&A", promote.match(item("Marvell Is Said to Near Deal for Lumentum In AI-Related Megadeal - Bloomberg.com", ents=("co-marvell",), pub="Bloomberg.com"))[0])
        self.assertIsNone(promote.match(item("Microsoft is offering buyouts to around 60,000 employees - Business Insider", ents=("co-microsoft",), pub="Business Insider")))

    def test_not_promoted(self):
        self.assertIsNone(promote.match(item("Broadcom shares slip in morning trade - Reuters")))
        self.assertIsNone(promote.match(item("Utility signs $12 billion pipeline deal - Reuters", ents=())))   # AI 문맥 없음
        self.assertIsNone(promote.match(item("Exclusive | Retailer weighs sale - Reuters", ents=(), pub="Reuters")))  # 감시 기업 없음

    def test_amount(self):
        self.assertEqual(promote.amount_billion("$63 billion and $21 billion"), 63)
        self.assertEqual(promote.amount_billion("a $1.2 trillion plan"), 1200)
        self.assertIsNone(promote.amount_billion("$900 million"))

    def test_signature_once_per_window(self):
        st = {}
        with mock.patch.object(promote.common, "load_state", side_effect=lambda n, d=None: st.setdefault(n, d or {})), \
             mock.patch.object(promote.common, "save_state", lambda n, data: st.__setitem__(n, data)):
            it = item("Anthropic IPO filing shows revenue surge - Reuters", ents=())
            now = datetime(2026, 10, 27, 6, 0, tzinfo=KST)
            self.assertIsNotNone(promote.check(it, now))
            self.assertIsNone(promote.check(item("What to know about the Anthropic IPO - Bloomberg", ents=()), now + timedelta(hours=3)))
            self.assertIsNotNone(promote.check(it, now + timedelta(hours=25)))


class TestDigest(unittest.TestCase):
    def test_build_ranks_and_excludes_korean(self):
        es = [{"level": "P2", "title": "Marvell Is Said to Near Deal for Lumentum - Bloomberg.com", "url": "u1", "entities": ["co-marvell"], "at": "2026-10-29T07:41:00+09:00"},
              {"level": "P2", "title": "Some vendor ships a part - TechSite", "url": "u2", "entities": [], "at": "2026-10-29T07:00:00+09:00"},
              {"level": "P1", "title": "삼성전기 영업익 165% 증가 - 데일리안", "url": "u3", "entities": ["co-semco"], "note": "매체 제한", "at": "2026-10-29T07:00:00+09:00"}]
        text = p2_digest.build(es, datetime(2026, 10, 30, 8, 5, tzinfo=KST))
        self.assertNotIn("삼성전기", text)                                   # 국내 언론 제외
        self.assertLess(text.index("Lumentum"), text.index("vendor"))        # 보유 종목·주요 매체가 위로
        self.assertIsNone(p2_digest.build([], datetime(2026, 10, 30, 8, 5, tzinfo=KST)))

    def test_once_a_day_in_window(self):
        with mock.patch.object(p2_digest.common, "load_state", return_value={"sent_day": "2026-10-30"}):
            self.assertEqual(p2_digest.run(now=datetime(2026, 10, 30, 8, 35, tzinfo=KST)), (0, False))
        with mock.patch.object(p2_digest.common, "load_state", return_value={}):
            self.assertEqual(p2_digest.run(now=datetime(2026, 10, 30, 14, 0, tzinfo=KST)), (0, False))


class TestPulseFinancing(unittest.TestCase):
    def test_financing_from_news_and_filings(self):
        fin, pubs = pulse._fin_cfg(), {"wsj", "reuters", "seeking alpha"}
        self.assertTrue(pulse.is_financing(item("Nvidia to Invest $3 Billion in Meta’s Equity Offering as They Expand AI Partnership - WSJ", ents=(), pub="WSJ"), fin, pubs))
        self.assertTrue(pulse.is_financing(item("Meta Announces Launch of Offering of Depositary Shares", ents=("co-meta",), doc="보도자료", sid="src-newsroom-meta"), fin, pubs))
        self.assertFalse(pulse.is_financing(item("Nvidia to invest $3 billion in Meta - SomeBlog", ents=(), pub="SomeBlog"), fin, pubs))   # 9개 매체 밖 기사
        self.assertFalse(pulse.is_financing(item("메타, 엔비디아 30억달러 투자 유치 - 한경", ents=("co-meta",), pub="한경"), fin, pubs))  # 국내 언론
        self.assertFalse(pulse.is_financing(item("Meta launches new Muse model - Reuters", ents=("co-meta",), pub="Reuters"), fin, pubs))  # 자금 조달 아님


if __name__ == "__main__":
    unittest.main()
