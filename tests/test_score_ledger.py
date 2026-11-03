"""인사이트 점수 성과 원장 시험 (마스터 지시 2026-11-04)"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "insight"))
import score_ledger as sl  # noqa: E402


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        sl.LEDGER = self.tmp / "ledger.csv"
        f = self.tmp / "20261103_1310_feed.json"
        f.write_text(json.dumps({"items": [{"code": "NVDA", "name": "엔비디아", "insight": 7, "dir": 1, "parts": {"novelty": 3}},
                                           {"code": "AMD", "name": "AMD", "insight": 5}]}), encoding="utf-8")
        self.feed = f

    def test_log_once(self):
        self.assertEqual(sl.log([self.feed]), 2)
        self.assertEqual(sl.log([self.feed]), 0)
        self.assertEqual(sl.rows()[0]["sent"], "2026-11-03T13:10+09:00")

    def test_resolve_ar(self):
        sl.log([self.feed])
        days = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]
        spy = [[d, 100.0] for d in days]
        nv = [[d, 100.0 + i] for i, d in enumerate(days)]
        sl.resolve({"SPY": spy, "NVDA": nv})
        r = sl.rows()[0]
        self.assertEqual(float(r["ar1"]), 1.0)   # 전날 종가 100 → 다음 거래일 101
        self.assertEqual(float(r["ar5"]), 5.0)
        self.assertEqual(r["ar20"], "")

    def test_fit_holds_small_sample(self):
        sl.log([self.feed])
        self.assertEqual(sl.fit()["n"], 0)


if __name__ == "__main__":
    unittest.main()
