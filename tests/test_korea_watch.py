"""한국 기업 미국 활동·해외 M&A 단서 (마스터 지시 2026-11-03)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar" / "usgov"))
import korea_watch as kw  # noqa: E402


class TestPages(unittest.TestCase):
    def test_docs_and_terms(self):
        html = '<a href="/a/minutes.pdf">Board <b>Project Solidigm</b></a><a href="/about">About</a>'
        got = kw.page_docs(html, "https://x.gov/m", ["Solidigm"])
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]["url"], "https://x.gov/a/minutes.pdf")
        self.assertEqual(got[0]["terms"], ["Solidigm"])


if __name__ == "__main__":
    unittest.main()
