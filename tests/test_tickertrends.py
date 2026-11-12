"""TickerTrends 수집기(radar/tickertrends.py) 오프라인 시험 — 2026-11-12 마스터 지시"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import tickertrends as tt  # noqa: E402
from pollers import common  # noqa: E402


class TestTickerTrends(unittest.TestCase):
    def setUp(self):
        self.saved, self.calls = [], []
        self.orig = (common.load_env, common.http_get, common.save_new_items, common.record_health, tt.OUT)
        common.load_env = lambda: {"TICKERTRENDS_API_KEY": "k"}
        common.save_new_items = lambda its: self.saved.extend(its) or its
        common.record_health = lambda *a, **k: None
        tt.OUT = Path(tempfile.mkdtemp())
        self.acc = 0.1

        def get(url, params=None, headers=None, timeout=0):
            self.calls.append((params, headers))
            return json.dumps({"status": "success", "signal": {"entity": params["entity"], "acceleration_90d": self.acc, "persistence_score": 82}}).encode()
        common.http_get = get

    def tearDown(self):
        common.load_env, common.http_get, common.save_new_items, common.record_health, tt.OUT = self.orig

    def test_key_in_header_and_alert_on_crossing(self):
        tt.run()                       # 첫 회차는 기준선 — 알림 없음
        self.assertEqual(self.saved, [])
        self.assertEqual(self.calls[0][1], {"Authorization": "Bearer k"})
        self.assertNotIn("k", json.dumps(self.calls[0][0]))   # 키는 주소에 없다
        self.acc = 0.3
        tt.run()                       # 문턱을 새로 넘으면 알림, 내부용 표시
        self.assertTrue(self.saved)
        self.assertTrue(all(i.get("internal_only") for i in self.saved))
        n = len(self.saved)
        tt.run()                       # 계속 넘어 있으면 다시 보내지 않는다
        self.assertEqual(len(self.saved), n)


if __name__ == "__main__":
    unittest.main()
