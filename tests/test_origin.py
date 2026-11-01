"""뉴스 원보도 추적 (마스터 지시 2026-11-02)"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))

import notify  # noqa: E402
import origin  # noqa: E402

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 29, 20, 30, tzinfo=KST)


def art(title, pub, ents=("co-marvell",), at="2026-10-29T07:37:00+09:00", iid=None):
    return {"item_id": iid or title[:20], "title": title, "publisher": pub, "url": "https://example.com/" + (iid or pub), "entities_matched": list(ents), "saved_at": at}


class TestCited(unittest.TestCase):
    def test_named_outlets(self):
        for title, pub, who in (("OpenAI Funding Target Cut by $10 Billion as AI Slumps, FT Says", "Bloomberg", "Financial Times"),
                                ("OpenAI plans to buy Google's AI chips, The Information reports - Reuters", "Reuters", "The Information"),
                                ("Financial Times reports Weil Gotshal faces collapse - CNBC", "CNBC", "Financial Times"),
                                ("Marvell in advanced talks to buy Lumentum, Bloomberg News reports - Reuters", "Reuters", "Bloomberg")):
            self.assertEqual(origin.cited({"title": title, "publisher": pub}), who)

    def test_unnamed_report(self):
        self.assertEqual(origin.cited({"title": "Marvell in advanced talks to buy Lumentum: Report - CNBC", "publisher": "CNBC"}), origin.GENERIC)
        self.assertEqual(origin.cited({"title": "Chip investment from Tesla, Nvidia, report says - Reuters", "publisher": "Reuters"}), origin.GENERIC)

    def test_not_relay(self):
        for title, pub in (("Ares CEO Says It's Avoiding Backing AI Chips, Citing Complexity", "Bloomberg"),
                           ("Micron Q1 earnings report", "Reuters"),
                           ("Nvidia CEO Reportedly Targeted By Suspected Informant - The Information", "The Information"),
                           ("18 stocks to play, according to a CIO - Business Insider", "Business Insider"),
                           ("Marvell Is Said to Near Megadeal for Lumentum in AI Push", "Bloomberg")):
            self.assertIsNone(origin.cited({"title": title, "publisher": pub}), title)


class TestApply(unittest.TestCase):
    def apply(self, item, rows, found=None):
        with mock.patch.object(origin, "pool", lambda now: rows), mock.patch.object(origin, "lookup", lambda i, w: found):
            return origin.apply(item, NOW)

    def test_swaps_to_collected_original(self):
        relay = art("Marvell in advanced talks to buy Lumentum, Bloomberg News reports - Reuters", "Reuters", at="2026-10-29T13:03:00+09:00", iid="relay")
        orig = art("Marvell Is Said to Near Deal for Lumentum In AI-Related Megadeal - Bloomberg.com", "Bloomberg.com", iid="orig")
        got = self.apply(relay, [relay, orig])
        self.assertEqual(got["url"], orig["url"])
        self.assertEqual((got["relay"]["outlet"], got["relay"]["carrier"], got["relay"]["found"]), ("Bloomberg", "Reuters", True))
        self.assertEqual(relay["url"], "https://example.com/relay")   # 수집 기록은 고치지 않는다

    def test_unnamed_relay_points_to_earlier_report(self):
        relay = art("Marvell in advanced talks to buy Lumentum: Report - CNBC", "CNBC", at="2026-10-29T20:27:00+09:00", iid="relay")
        orig = art("Marvell Is Said to Near Deal for Lumentum In AI-Related Megadeal - Bloomberg.com", "Bloomberg.com", iid="orig")
        got = self.apply(relay, [relay, orig])
        self.assertTrue(got["relay"]["inferred"])
        self.assertIn("먼저 나온 보도 Bloomberg", origin.line(got["relay"]))

    def test_other_story_of_same_company_is_not_original(self):
        relay = art("Marvell in advanced talks to buy Lumentum: Report - CNBC", "CNBC", at="2026-10-29T20:27:00+09:00", iid="relay")
        other = art("Marvell Raises Custom Chip Outlook", "Bloomberg", iid="other")
        self.assertFalse(self.apply(relay, [relay, other])["relay"]["found"])

    def test_later_article_is_not_original(self):
        relay = art("Marvell in advanced talks to buy Lumentum, Bloomberg News reports - Reuters", "Reuters", at="2026-10-29T08:00:00+09:00", iid="relay")
        later = art("Marvell in Talks to Buy Nvidia-Backed Lumentum", "Bloomberg", at="2026-10-30T01:06:00+09:00", iid="later")
        self.assertFalse(self.apply(relay, [relay, later])["relay"]["found"])

    def test_uncollected_outlet_uses_index(self):
        relay = art("OpenAI Funding Target Cut by $10 Billion as AI Slumps, FT Says", "Bloomberg", ("us-openai",), iid="relay")
        got = self.apply(relay, [relay], {"title": "OpenAI cuts funding target by $10bn", "url": "https://news.google.com/x", "publisher": "Financial Times"})
        self.assertEqual((got["url"], got["relay"]["found"]), ("https://news.google.com/x", True))

    def test_not_found_keeps_relay_and_says_so(self):
        relay = art("OpenAI Funding Target Cut by $10 Billion as AI Slumps, FT Says", "Bloomberg", ("us-openai",), iid="relay")
        got = self.apply(relay, [relay])
        self.assertEqual(got["url"], relay["url"])
        self.assertIn("원보도 Financial Times(원문 못 찾음)", origin.line(got["relay"]))

    def test_non_relay_untouched(self):
        item = art("Marvell Is Said to Near Megadeal for Lumentum", "Bloomberg")
        self.assertIs(self.apply(item, []), item)


class TestAlert(unittest.TestCase):
    def test_alert_shows_path(self):
        item = art("FT article", "Financial Times", ("us-openai",), iid="x")
        item.update(relay={"outlet": "Financial Times", "carrier": "Bloomberg", "relay_url": "https://b.example/a?x=1&y=2", "found": True})
        text = notify.format_item("P1", item)
        self.assertIn('원보도 Financial Times · 재인용 <a href="https://b.example/a?x=1&amp;y=2">Bloomberg</a>', text)


if __name__ == "__main__":
    unittest.main()
