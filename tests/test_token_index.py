"""LLM 토큰 가격 지수(마스터 지시 2026-11-22 "Token Price Index도 수집해봐. 매주 일요일 오후 6시에 보내줘.")"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import token_index as T  # noqa: E402

PAGE = ('"points":[{"date":"2026-11-13","price":0.8052},{"date":"2026-11-20","price":0.6793}],"href":"/products/silicon-index/llm-token-expenditure-index","caption":"x"'
        ' "points":[{"date":"2026-11-20","price":0.3821}],"href":"/products/silicon-index/llm-token-expenditure-index?series=open-llm","caption":"y"').replace('"', '\\"')
KST = timezone(timedelta(hours=9))


class Token(unittest.TestCase):
    def test_latest_reads_headline_and_week_ago(self):
        got = T.latest(PAGE)
        self.assertEqual((got["date"], got["blended"], got["open"], got["wk_ago"]), ("2026-11-20", 0.6793, 0.3821, 0.8052))

    def test_due_only_sunday_evening_once(self):
        rs = [{"date": "2026-11-20", "value": 0.6793, "wk_ago_date": "2026-11-13", "wk_ago": "0.8052"}]
        with mock.patch.object(T, "rows", return_value=rs), mock.patch.object(T.common, "load_state", return_value={}):
            self.assertFalse(T.status(datetime(2026, 11, 22, 17, 0, tzinfo=KST))["due"])
            s = T.status(datetime(2026, 11, 22, 18, 5, tzinfo=KST))
            self.assertTrue(s["due"])
            self.assertAlmostEqual(s["wow"], -0.1564, places=3)
        with mock.patch.object(T, "rows", return_value=rs), mock.patch.object(T.common, "load_state", return_value={"sent_week": "2026-W47"}):
            self.assertFalse(T.status(datetime(2026, 11, 22, 19, 0, tzinfo=KST))["due"])


if __name__ == "__main__":
    unittest.main()
