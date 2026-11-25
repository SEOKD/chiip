"""국내 전자 기업 해외 법인 소식(2026-11-26 마스터 지시)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import overseas_subs as O  # noqa: E402


class TestMatch(unittest.TestCase):
    def setUp(self):
        self.m = O.matcher()

    def test_hits(self):
        self.assertEqual(self.m("LG전자 인도법인 지분 2% 추가 매각")[0], "co-lg-electronics")
        self.assertEqual(self.m("LG Electronics India promoter may offload 2% stake")[0], "co-lg-electronics")
        self.assertEqual(self.m("Samsung Electronics' Vietnam plant cuts output")[0], "co-samsung-electronics")
        self.assertEqual(self.m("솔리다임, 신규 eSSD 출시")[0], "co-skhynix")
        self.assertEqual(self.m("삼성전기 필리핀 공장 증설")[0], "co-semco")

    def test_misses(self):
        self.assertIsNone(self.m("삼성전자 HBM4 엔비디아 퀄 통과"))
        self.assertIsNone(self.m("LG Electronics unveils new OLED TV lineup"))

    def test_rss(self):
        x = O.parse_rss("<rss><item><title><![CDATA[LG Electronics India stake sale]]></title><link>https://b.example/a</link>"
                        "<description>x</description><pubDate>Wed, 25 Nov 2026 19:15:21 +0530</pubDate></item></rss>")
        self.assertEqual((x[0]["title"], x[0]["pub"][:10]), ("LG Electronics India stake sale", "2026-11-25"))


if __name__ == "__main__":
    unittest.main()
