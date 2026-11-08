"""숏 캠페인 대상 회사 사이트 감시 — Cerebras 반박 블로그(2026-11-05) 재연(2026-11-09 시의성 점검)"""
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import company_sites as C  # noqa: E402

CFG = {"target_lookback_h": 72, "target_sites": [{"company": "Cerebras", "entity_ids": ["us-cbrs"], "sitemap": "https://x/sitemap.xml", "path": "/blog/"}]}
OLD = [("https://www.cerebras.ai/blog/moe-guide", datetime(2026, 10, 22, tzinfo=timezone.utc)), ("https://www.cerebras.ai/pricing", datetime(2026, 11, 1, tzinfo=timezone.utc))]
NEW = OLD + [("https://www.cerebras.ai/blog/what-it-took-to-build-wafer-scale-and-why-it-lasts", datetime(2026, 11, 5, 14, tzinfo=timezone.utc))]


class TestCompanySites(unittest.TestCase):
    def test_new_blog_post_caught_once(self):
        state = {}
        real = C.common.load_yaml
        with mock.patch.object(C.common, "load_yaml", side_effect=lambda p: CFG if "short_watch" in p else real(p)), mock.patch.object(C, "_robots_ok", return_value=True), \
                mock.patch.object(C.common, "load_state", side_effect=lambda n, d: state.get(n, d)), \
                mock.patch.object(C.common, "save_state", side_effect=lambda n, v: state.__setitem__(n, v)):
            T = datetime(2026, 11, 5, 14, 10, tzinfo=timezone.utc)
            with mock.patch.object(C, "entries", return_value=OLD):
                self.assertEqual(C.poll(now=T), [])                                  # 첫 회차는 기준선
            with mock.patch.object(C, "entries", return_value=NEW):
                items = C.poll(now=T)
                self.assertEqual(len(items), 1)                                 # 반박 블로그를 게시 10분 뒤에 잡는다
                self.assertIn("what-it-took", items[0]["url"])
                self.assertEqual(C.poll(now=T), [])                                  # 같은 글을 두 번 내지 않는다


if __name__ == "__main__":
    unittest.main()
