"""30분 펄스(radar/pulse.py) 결정론 관문 오프라인 시험 — 마스터 지시 2026-10-28"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))

import pulse  # noqa: E402

KST = timezone(timedelta(hours=9))


class TestPulse(unittest.TestCase):
    def test_only_primary_sources(self):
        self.assertEqual(pulse.class_of("src-arxiv-csar"), "논문")
        self.assertEqual(pulse.class_of("src-prn"), "보도자료")
        self.assertEqual(pulse.class_of("src-newsroom-nvidia"), "보도자료")
        self.assertEqual(pulse.class_of("src-sec-deals"), "공시")
        self.assertEqual(pulse.class_of("src-whitehouse"), "정부")
        self.assertIsNone(pulse.class_of("src-news7-focus"))          # 기사는 원본이 아니다
        self.assertIsNone(pulse.class_of("src-gnews-t0-en"))
        self.assertIsNone(pulse.class_of("src-newsroom-skhynix-ko"))  # 영어권 중심
        self.assertIsNone(pulse.class_of("src-policy-cn"))

    def test_relevance_filter(self):
        en = {"title": "Acme ships co-packaged optics switch for AI clusters (NASDAQ: ACME)", "language": "en", "snippet": ""}
        de = {"title": "Infosys schließt die SAP-Umstellung für Syngenta ab", "language": "en", "snippet": ""}
        off = {"title": "Regional bank reports quarterly dividend", "language": "en", "snippet": ""}
        self.assertTrue(pulse.relevant(en, "보도자료"))
        self.assertFalse(pulse.relevant(de, "보도자료"))
        self.assertFalse(pulse.relevant(off, "보도자료"))
        self.assertTrue(pulse.relevant(off, "공시"))   # 공시는 업종(SIC)으로 이미 걸러짐

    def test_score_prefers_deals_over_periodic(self):
        deal = {"title": "[SEC 8-K 1.01 중요 계약] Acme (ACME)", "sec_items": "1.01", "snippet": ""}
        tenq = {"title": "[SEC 10-Q 10-Q] Acme", "snippet": ""}
        self.assertGreater(pulse.score(deal, "공시"), pulse.score(tenq, "공시"))

    def test_candidates_exclude_watchlist(self):
        src = [{"title": "Big Co picks Tiny Co (NASDAQ: TINY) and Nvidia (NASDAQ: NVDA)", "snippet": "", "url": "u1", "source_id": "src-prn"},
               {"title": "[SEC 8-K 1.01] Tiny Co (TINY)", "snippet": "", "url": "u2", "source_id": "src-sec-deals", "ticker": "TINY"}]
        c = pulse.candidates(src, {"NVDA": "co-nvidia"})
        self.assertEqual([x["ticker"] for x in c], ["TINY"])
        self.assertEqual(c[0]["id"], "us-tiny")
        self.assertEqual(c[0]["urls"], ["u1", "u2"])

    def test_queue_busy_window(self):
        self.assertTrue(pulse.queue_busy(datetime(2026, 10, 29, 8, 20, tzinfo=KST)))
        self.assertTrue(pulse.queue_busy(datetime(2026, 10, 29, 18, 40, tzinfo=KST)))
        self.assertFalse(pulse.queue_busy(datetime(2026, 10, 29, 9, 0, tzinfo=KST)))


if __name__ == "__main__":
    unittest.main()
