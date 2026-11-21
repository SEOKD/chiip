"""영국 회사 IR 공시 피드(마스터 지시 2026-11-22 "1번 기준으로 파이프라인을 만들어라")"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import common, uk_ir as U  # noqa: E402

XML = """﻿<?xml version="1.0" encoding="UTF-8"?><Results><RNSSummaries>
<RNSSummary><Title><![CDATA[Half-year Report]]></Title><ShareURL><![CDATA[https://x/story?newsid=2]]></ShareURL><pubDate>Tue, 17 Nov 2026 07:00:00 GMT</pubDate></RNSSummary>
<RNSSummary><Title><![CDATA[Transaction in Own Shares]]></Title><ShareURL><![CDATA[https://x/story?newsid=1]]></ShareURL><pubDate>Tue, 17 Nov 2026 07:00:00 GMT</pubDate></RNSSummary>
</RNSSummaries></Results>"""


class UkIr(unittest.TestCase):
    def test_parsers(self):
        r = U.parse_investis(XML)
        self.assertEqual((r[0]["title"], r[0]["date"][:10]), ("Half-year Report", "2026-11-17"))
        d = U.parse_dp(json.dumps([{"title": "Holding(s) in Company", "url": "/viewer/124/1", "publishedAt": "2026-11-20T17:30:00+00:00", "category": "HOL"}]),
                       "https://ir.design-portfolio.co.uk/api/companies/124/articles")
        self.assertEqual(d[0]["link"], "https://ir.design-portfolio.co.uk/viewer/124/1")
        h = U.parse_html('<span class="news-date"> 19 November 2026 </span><p><a class="content-link" href="/news/a"> Half Year Results </a>', "https://www.halma.com/news")
        self.assertEqual((h[0]["title"], h[0]["link"]), ("Half Year Results", "https://www.halma.com/news/a"))

    def test_baseline_then_new_only_and_routine_skipped(self):
        mem = {}
        co = [{"tidm": "QQ.", "id": "co-qinetiq", "name": "QinetiQ", "kind": "investis", "feed": "https://otp.tools.investis.com/x"}]
        with mock.patch.object(common, "load_state", side_effect=lambda n, d=None: mem.get(n, d)), \
                mock.patch.object(common, "save_state", side_effect=lambda n, v: mem.__setitem__(n, v)), \
                mock.patch.object(U, "cfg", return_value=co), mock.patch.object(U, "robots_ok", return_value=True), \
                mock.patch.object(U, "LOOKBACK_H", 10 ** 6):
            self.assertEqual(U.poll(get=lambda u: XML.replace("newsid=2", "newsid=0")), [])   # 첫 회차 기준선
            got = U.poll(get=lambda u: XML)
        self.assertEqual([i["title"] for i in got], ["[RNS] QinetiQ(QQ): Half-year Report"])   # 자사주 정례 공시는 뺀다


if __name__ == "__main__":
    unittest.main()
