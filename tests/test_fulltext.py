"""원문 열람 — SEC 403 사유·대체 와이어·숫자 문장·재시도 (마스터 지시 2026-11-13)"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import fulltext as F  # noqa: E402
from pollers import common  # noqa: E402

KST = timezone(timedelta(hours=9))
PR = ("<html><nav>menu</nav><p>ARLINGTON, Va., Nov. 12, 2026 /PRNewswire/ -- Corvex, Inc. (Nasdaq: MOVE) today reported results.</p>"
      "<p>Total revenue for the third quarter was $5.0 million, up 31% from $3.8 million in the second quarter of 2026.</p>"
      "<p>Contracted annualized revenue on live compute was approximately $21.7 million as of November 12, 2026.</p>"
      + "<p>filler text about the company and its platform for AI workloads.</p>" * 10 + "</html>")
SEC_ITEM = {"item_id": "src-sec-filings:0001", "source_id": "src-sec-filings", "doc_type": "실적", "title": "[SEC 8-K 실적] Corvex, Inc.",
            "url": "https://www.sec.gov/Archives/edgar/data/1/0001/x-8k.htm", "sec_items": "2.02,9.01", "entities_matched": ["us-move"]}


class TestFulltext(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inbox = Path(self.tmp.name)
        day = self.inbox / "20261113"
        day.mkdir()
        (day / "src-prn_abc.json").write_text(json.dumps({"item_id": "src-prn:abc", "source_id": "src-prn", "title": "Corvex Reports Third Quarter 2026 Results",
                                                         "url": "https://www.prnewswire.com/x.html", "snippet": "ARLINGTON, Va., Nov. 12, 2026 /PRNewswire/ -- Corvex",
                                                         "ticker": "Nasdaq: MOVE", "published_at": "2026-11-12T13:05:00+00:00"}), encoding="utf-8")
        self.p = [mock.patch.object(common, "INBOX", self.inbox), mock.patch.object(F, "sec_ua", lambda: None),
                  mock.patch.object(F, "_get", lambda url, ua=None, timeout=20: PR)]
        for x in self.p:
            x.start()
        self.now = datetime(2026, 11, 13, 9, tzinfo=KST)

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def test_sec_403_falls_back_to_wire(self):
        ft = F.fetch(dict(SEC_ITEM), self.now)
        self.assertEqual(ft["status"], "ok")
        self.assertEqual(ft["route"], "대체: src-prn")
        self.assertIn("SEC_USER_AGENT", ft["note"])
        self.assertTrue(any("$5.0 million" in k for k in ft["kpi"]))
        self.assertNotIn("menu", ft["excerpt"][:50])

    def test_fail_reason_when_no_wire(self):
        it = dict(SEC_ITEM, title="[SEC 8-K 실적] Nobody Corp", entities_matched=["us-zzzz"])
        ft = F.fetch(it, self.now)
        self.assertEqual(ft["status"], "fail")
        self.assertIn("SEC 403", ft["why"])
        self.assertIn("Fiscal.ai", ft["hint"])
        self.assertTrue(F.card_text(ft).startswith("본문 미확인 — SEC 403"))

    def test_enrich_caches_and_queues_retry(self):
        states = {}
        with mock.patch.object(common, "load_state", lambda n, d=None: states.get(n, d if d is not None else {})), \
                mock.patch.object(common, "save_state", lambda n, v: states.__setitem__(n, v)):
            it = dict(SEC_ITEM, title="[SEC 8-K 실적] Nobody Corp", entities_matched=["us-zzzz"])
            F.enrich([it], self.now)
            self.assertIn(it["item_id"], states[F.RETRY])
            calls = []
            F.enrich([dict(it, fulltext=None)], self.now + timedelta(minutes=5), fetcher=lambda i, n: calls.append(1) or {"status": "ok", "kpi": []})
            self.assertEqual(calls, [])   # 재시도 간격 전에는 캐시
            F.enrich([dict(it, fulltext=None)], self.now + timedelta(minutes=61), fetcher=lambda i, n: calls.append(1) or {"status": "ok", "kpi": []})
            self.assertEqual(calls, [1])
            self.assertNotIn(it["item_id"], states[F.RETRY])

    def test_sec_with_ua_reads_exhibit(self):
        pages = {"https://www.sec.gov/Archives/edgar/data/1/0001/x-8k.htm": "<p>Item 2.02 Results of Operations. See Exhibit 99.1.</p>",
                 "https://www.sec.gov/Archives/edgar/data/1/0001/index.json": json.dumps({"directory": {"item": [{"name": "x-8k.htm"}, {"name": "ex99-1.htm"}]}}),
                 "https://www.sec.gov/Archives/edgar/data/1/0001/ex99-1.htm": PR}
        with mock.patch.object(F, "sec_ua", lambda: "Test UA test@example.com"), \
                mock.patch.object(F, "_get", lambda url, ua=None, timeout=20: pages[url]), mock.patch.object(F.time, "sleep", lambda s: None):
            ft = F.fetch(dict(SEC_ITEM), self.now)
        self.assertEqual(ft["route"], "SEC 원문+EX-99")
        self.assertTrue(any("$21.7 million" in k for k in ft["kpi"]))


if __name__ == "__main__":
    unittest.main()
