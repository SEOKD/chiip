"""13F 시즌 → Pulse 기관 매입·매도 순위 (마스터 지시 2026-11-08)"""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import thirteenf as tf  # noqa: E402

C = {"rounds": [{"name": "잠정", "offset": -2}, {"name": "주", "offset": 1}, {"name": "확정", "offset": 7}], "batch": 2, "top": 2, "min_holders": 30}


class TestThirteenF(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._s, self._o, self._u, self._c = tf.STATE, tf.OUT, tf.universe, tf.cfg
        tf.STATE, tf.OUT = self.tmp / "st.json", self.tmp / "out"
        tf.universe = lambda c=None: ["NASDAQ_AAA", "NYSE_BBB", "NASDAQ_CCC"]
        tf.cfg = lambda: C

    def tearDown(self):
        tf.STATE, tf.OUT, tf.universe, tf.cfg = self._s, self._o, self._u, self._c

    def test_deadline_weekend_rolls(self):
        self.assertEqual(tf.deadline(2026, 3), date(2026, 11, 16))   # 11-14 토요일 → 월요일
        self.assertEqual(tf.deadline(2026, 2), date(2026, 8, 14))

    def test_quiet_outside_season(self):
        self.assertFalse(tf.status(datetime(2026, 10, 1, 9, tzinfo=tf.KST))["due"])

    def test_collect_put_rank_send(self):
        now = datetime(2026, 11, 17, 9, tzinfo=tf.KST)
        s = tf.status(now)
        self.assertEqual((s["phase"], s["quarter"], s["round"]), ("collect", "2026Q3", "주"))
        _, bodies = tf.plan(now, C)
        self.assertEqual(len(bodies), 2)
        self.assertIn('"NASDAQ_AAA"', bodies[0])
        self.assertNotIn("__KEYS__", bodies[0])
        rows = [{"key": "NASDAQ_AAA", "quarter": "2026Q3", "holders": 900, "covered": 900, "increased": 500, "decreased": 300},
                {"key": "NYSE_BBB", "quarter": "2026Q3", "holders": 400, "covered": 400, "increased": 100, "decreased": 350},
                {"key": "NASDAQ_CCC", "quarter": "2026Q3", "error": "x"}]
        f = self.tmp / "o.txt"
        f.write_text("log\n" + json.dumps(rows), encoding="utf-8")
        self.assertEqual(tf.put(f, now), 2)
        self.assertEqual(tf.status(now)["phase"], "send")
        r = tf.rank("2026Q3", C)
        self.assertEqual([x["ticker"] for x in r["buy"]], ["AAA", "BBB"])
        self.assertEqual([x["ticker"] for x in r["sell"]], ["BBB", "AAA"])
        msg = tf.message(now, C)
        self.assertIn("매입(보유를 늘린) 기관 수 상위", msg)
        self.assertIn("순매도 250곳", msg)
        tf.sent(now)
        self.assertFalse(tf.status(now)["due"])
        self.assertTrue(tf.status(datetime(2026, 11, 23, 9, tzinfo=tf.KST))["due"])   # 확정 차례는 다시 연다


if __name__ == "__main__":
    unittest.main()
