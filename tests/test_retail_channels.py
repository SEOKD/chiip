"""리테일 채널 집계 (마스터 지시 2026-11-01)"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import attention  # noqa: E402
import retail_channels as rc  # noqa: E402

RSS = '<rss><channel><item><title>Acme earnings</title></item></channel></rss>'


def fake(url):
    if "apewisdom" in url:
        return json.dumps({"pages": 1, "results": [{"ticker": "ACM", "mentions": 12}]})
    if "tradestie" in url:
        return json.dumps([{"ticker": "ACM", "sentiment": "Bullish", "no_of_comments": 30}])
    if "wikimedia" in url:
        return json.dumps({"items": [{"views": 10}, {"views": 5}]})
    if "algolia" in url:
        return json.dumps({"nbHits": 4})
    if "lemmy" in url:
        return json.dumps({"posts": [{"post": {"published": "2999-01-01T00:00:00"}}, {"post": {"published": "2000-01-01T00:00:00"}}]})
    if "twse" in url:
        return json.dumps([{"股票代號": "2330", "融資今日餘額": "1,234"}])
    if "trends.google" in url:
        return RSS
    if "arctic-shift" in url:
        return json.dumps({"data": [{"title": "Nvidia earnings"}]})
    if "kalshi" in url:
        return json.dumps({"events": [{"title": "Fed cut in December?", "category": "Economics", "markets": [{"yes_ask_dollars": "0.40", "yes_sub_title": "Cut"}]}, {"title": "Fed Cup winner", "category": "Sports", "markets": []}, {"title": "Jaime's AIr", "category": "Economics", "markets": []}]})
    raise ValueError(url)


class TestCollect(unittest.TestCase):
    def test_counts_only_and_market_snapshot(self):
        cands = {"us-acme": {"name": "Acme", "code": "ACM.US", "market": "us"}, "tw-tsmc": {"name": "TSMC", "code": "2330", "market": "tw"}}
        rows, notes, snap = rc.collect(cands, "2026-11-01", fetch=fake, pause=0)
        got = {(r[1], r[2]): r[3] for r in rows}
        self.assertEqual(got[("us-acme", "reddit_mentions")], 12)
        self.assertEqual(got[("us-acme", "wsb_comments")], 30)
        self.assertEqual(got[("us-acme", "wiki_views")], 15)
        self.assertEqual(got[("us-acme", "hn")], 4)
        self.assertEqual(got[("us-acme", "lemmy")], 1)
        self.assertEqual(got[("us-acme", "trends_hit")], 1)
        self.assertEqual(got[("tw-tsmc", "margin_tw")], 1234)
        self.assertNotIn(("tw-tsmc", "reddit_mentions"), got)
        self.assertEqual(snap["wsb_sentiment"]["ACM"], "Bullish")
        self.assertEqual([m["title"] for m in snap["kalshi"]], ["Fed cut in December?"])
        self.assertEqual(snap["kalshi"][0]["yes"], 0.4)
        self.assertEqual(notes, [])

    def test_one_source_failing_keeps_the_rest(self):
        def broken(url):
            if "apewisdom" in url:
                raise OSError("down")
            return fake(url)
        rows, notes, _ = rc.collect({"us-acme": {"name": "Acme", "code": "ACM.US"}}, "2026-11-01", fetch=broken, pause=0)
        self.assertTrue(any("ape_all" in n for n in notes))
        self.assertTrue(any(r[2] == "wiki_views" for r in rows))
        self.assertFalse(any(r[2] == "reddit_mentions" for r in rows))


class TestNames(unittest.TestCase):
    def test_short_name_and_us_ticker(self):
        self.assertEqual(rc.short_name("CACI International"), "CACI")
        self.assertEqual(rc.short_name("Taiwan Semiconductor Manufacturing Co., Ltd."), "Taiwan Semiconductor Manufacturing")
        self.assertEqual(rc.us_ticker({"code": "FORM", "market": "us"}), "FORM")
        self.assertIsNone(rc.us_ticker({"code": "6976", "market": "jp"}))
        self.assertIsNone(rc.us_ticker({"code": "2330", "market": "tw"}))


class TestAttention(unittest.TestCase):
    def test_level_sources_do_not_swamp_crowding(self):
        rows = [("2026-11-01", "a", "wiki_views", 900000), ("2026-11-01", "a", "reddit_mentions", 1), ("2026-11-01", "b", "reddit_mentions", 50)]
        out = attention.summarize(rows, "2026-11-01")
        self.assertEqual(out["a"]["investor"], 1)
        self.assertEqual(out["a"]["saturated"], [])
        self.assertGreater(out["b"]["crowding_pct"], out["a"]["crowding_pct"])


if __name__ == "__main__":
    unittest.main()
