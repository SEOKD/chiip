"""API 키 만료 알림 시험 (2026-11-22)"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import key_expiry as ke  # noqa: E402

ENV = {"USITC_DATAWEB_TOKEN": "x", "CENSUS_API_KEY": "x"}


class T(unittest.TestCase):
    def test_quiet_when_far(self):
        self.assertEqual(ke.check(date(2026, 12, 1), ENV, {}, []), [])

    def test_reminds_once_per_threshold(self):
        a = ke.check(date(2027, 4, 21), ENV, {}, [])   # 만료 2027-05-20, 29일 남음 → 30일 문턱
        self.assertEqual(len(a), 1)
        self.assertIn("29일 남음", a[0][0])
        self.assertEqual(ke.check(date(2027, 4, 22), ENV, {}, [a[0][1]]), [])
        self.assertEqual(len(ke.check(date(2027, 5, 7), ENV, {}, [a[0][1]])), 1)   # 14일 문턱

    def test_missing_key_not_alerted(self):
        self.assertEqual(ke.check(date(2027, 5, 19), {}, {}, []), [])

    def test_auth_error_alert(self):
        h = {"src-trade-share": {"error_count": 3, "last_error": "2026-12-01 HTTPError 403 Forbidden"}}
        a = ke.check(date(2026, 12, 1), ENV, h, [])
        self.assertTrue(any("Census" in m for m, _ in a))
        h["src-trade-share"]["last_error"] = "timeout"
        self.assertEqual(ke.check(date(2026, 12, 1), ENV, h, []), [])


if __name__ == "__main__":
    unittest.main()
