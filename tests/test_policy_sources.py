"""정책·학회 원천(§21.12) — rss.poll_source의 include_regex·max_age_days·부분 실패 처리 오프라인 테스트"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))

from pollers import common, rss  # noqa: E402

FMT = "%a, %d %b %Y %H:%M:%S +0900"


def feed(rows):
    body = "".join(f"<item><title>{t}</title><link>https://gov.example/{i}</link><pubDate>{d}</pubDate>"
                   f"<description>{t}</description></item>" for i, (t, d) in enumerate(rows))
    return f"<rss><channel>{body}</channel></rss>".encode()


class TestPolicyPoll(unittest.TestCase):
    def setUp(self):
        now = common.now_kst()
        self.fresh, self.old = now.strftime(FMT), (now - timedelta(days=30)).strftime(FMT)

    def test_regex_and_age(self):
        src = {"id": "src-policy-cn", "feed_url": "https://a/feed", "doc_type": "규제·정책", "language": "zh",
               "include_regex": "半导体|出口管制", "max_age_days": 3}
        raw = feed([("商务部 出口管制 公告", self.fresh), ("反倾销 铝箔", self.fresh), ("半导体 旧公告", self.old)])
        with mock.patch.object(common, "http_get", return_value=raw):
            items = rss.poll_source(src)
        self.assertEqual([i["title"] for i in items], ["商务部 出口管制 公告"])
        self.assertEqual(items[0]["doc_type"], "규제·정책")

    def test_one_feed_down_others_kept(self):
        src = {"id": "src-assoc-feeds", "feed_urls": ["https://ok/feed", "https://down/feed"], "doc_type": "학회·협회"}

        def get(url, *a, **k):
            if "down" in url:
                raise OSError("down")
            return feed([("JEDEC HBM4E standard", self.fresh)])
        with mock.patch.object(common, "http_get", side_effect=get):
            self.assertEqual(len(rss.poll_source(src)), 1)
        with mock.patch.object(common, "http_get", side_effect=OSError("down")):
            with self.assertRaises(RuntimeError):
                rss.poll_source(src)

    def test_registry_sources_valid(self):
        import re
        reg = [s for s in common.load_yaml("config/source_registry.yaml") if s["id"].startswith(("src-policy", "src-assoc"))]
        self.assertGreaterEqual(len(reg), 10)
        for s in reg:
            self.assertIn(s["doc_type"], ("규제·정책", "학회·협회"))
            self.assertTrue(s.get("feed_url") or s.get("feed_urls") or s.get("feed_queries"), s["id"])
            if s.get("include_regex"):
                re.compile(s["include_regex"])


if __name__ == "__main__":
    unittest.main()
