"""상장사 IR 보도자료 피드 — 추측한 호스트가 남의 회사면 거른다(2026-11-11, AAOI → ir.applied.com 오매칭)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import ir_press as m  # noqa: E402

FEED = b'<?xml version="1.0"?><rss version="2.0"><channel><item><title>Applied Industrial Technologies Reports Results</title><link>https://x/1</link><description>d</description></item></channel></rss>'


class T(unittest.TestCase):
    def test_other_company_feed_rejected(self):
        m.NAMES.update({"AAOI": "Applied Optoelectronics, Inc.", "AIT": "Applied Industrial Technologies, Inc."})
        self.assertFalse(m.is_feed(FEED, "AAOI"))
        self.assertTrue(m.is_feed(FEED, "AIT"))
        self.assertTrue(m.is_feed(FEED))

    def test_guess_hosts(self):
        m.NAMES["NVDA"] = "NVIDIA Corporation"
        self.assertIn("investor.nvidia.com", m.guess_hosts("NVDA"))


if __name__ == "__main__":
    unittest.main()
