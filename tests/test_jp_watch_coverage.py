"""와치리스트 도쿄 종목은 모두 일본 감시 목록(config/jp_watch.yaml)에 있어야 한다 (마스터 점검 2026-11-14 — santec 11/6 실적·11/13 반기보고서 미탐지)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import tv_sync  # noqa: E402


class TestJpCoverage(unittest.TestCase):
    def test_every_tse_watchlist_name_is_watched(self):
        self.assertEqual(tv_sync.jp_gaps(), [])

    def test_santec_is_not_the_other_suntec(self):
        from pollers import common
        c = next(x for x in common.load_yaml("config/jp_watch.yaml")["companies"] if x["code"] == "6777")
        self.assertNotIn("サンテック", c["ja"])   # サンテック = 1960(전기공사) — 다른 회사 제목을 잡는다


if __name__ == "__main__":
    unittest.main()
