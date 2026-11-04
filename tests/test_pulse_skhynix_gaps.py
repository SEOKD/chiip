"""SK하이닉스 뉴욕 보도 4시간 지연 점검 후속 시험 (마스터 지시 2026-11-04)"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "radar" / "usgov"))
import korea_watch as kw  # noqa: E402
import run_poll  # noqa: E402
from pollers import common, sec_filings  # noqa: E402

CFG = {"companies": {"co-skhynix": ["SK hynix", "Solidigm"]}}


class T(unittest.TestCase):
    def test_new_13d_form_name_watched(self):
        self.assertIn("SCHEDULE 13D", sec_filings.FORMS)
        self.assertIn("6-K", sec_filings.FORMS)

    def test_skhynix_has_sec_ticker(self):
        uni = {u["id"]: u for u in common.load_yaml("config/valuation.yaml")["universe"]}
        self.assertEqual(sec_filings.ticker_of(uni["co-skhynix"]), "SKHY")

    def test_news_mode_skips_nav_and_keeps_named_release(self):
        html = ('<a href="/marcy">Marcy Nano</a><a href="/cdn-cgi/l/email-protection#x">Solidigm press contact at the ESD office</a>'
                '<a href="/news/1">Governor announces Solidigm Marcy site review update</a>')
        docs = kw.page_docs(html, "https://esd.ny.gov/", ["Solidigm", "Marcy"], "news")
        self.assertEqual([d["url"] for d in docs], ["https://esd.ny.gov/news/1"])

    def test_to_items_routes_gov_and_news(self):
        rows = [{"type": "회의 자료", "juris": "뉴욕주", "url": "https://x/a.pdf", "title": "Board materials Solidigm", "terms": ["Solidigm"]},
                {"type": "회의 자료", "juris": "뉴욕주", "url": "https://x/b.pdf", "title": "Board materials", "terms": []},
                {"type": "언론 제목", "query": "q", "title": "SK hynix Dalian license on hold - Reuters", "url": "https://n/1", "pub": "Tue, 03 Nov 2026 19:03:00 GMT"},
                {"type": "언론 제목", "query": "q", "title": "Unrelated chip news", "url": "https://n/2", "pub": None}]
        out = kw.to_items(rows, CFG)
        self.assertEqual([i["source_id"] for i in out], ["src-policy-us-kw", "src-kw-news"])
        self.assertEqual(out[0]["doc_type"], "정부")
        self.assertTrue(out[1]["published_at"].startswith("2026-11-04T04:03"))

    def test_sweep_baseline_then_refeed_unjudged(self):
        tmp = Path(tempfile.mkdtemp())
        day = common.now_kst().strftime("%Y%m%d")
        (tmp / "inbox" / day).mkdir(parents=True)
        (tmp / "state").mkdir()

        def put(iid):
            (tmp / "inbox" / day / f"{iid}.json").write_text(json.dumps({"item_id": iid, "saved_at": common.iso(common.now_kst())}), encoding="utf-8")
        put("a")
        with mock.patch.object(common, "INBOX", tmp / "inbox"), mock.patch.object(common, "STATE", tmp / "state"):
            self.assertEqual(run_poll.fast_sweep(), [])            # 첫 실행 = 기준선
            put("b")
            self.assertEqual([i["item_id"] for i in run_poll.fast_sweep()], ["b"])
            run_poll.fast_log([({"item_id": "b", "title": "t"}, "규칙 없음")])
            self.assertEqual(run_poll.fast_sweep(), [])
            self.assertIn("규칙 없음", (tmp / "state" / "fast_lane.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
