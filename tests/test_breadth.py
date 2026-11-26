"""시장 폭 경보(2026-11-26 마스터 지시 "경보형으로 구축")"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import breadth as B  # noqa: E402

KST = timezone(timedelta(hours=9))


def rows(a200s, ad=(50, 50)):
    return [{"date": f"2026-0{1 + i // 28}-{1 + i % 28:02d}", "nh": 2, "nl": 1, "a20": 50, "a50": 50, "a200": v,
             "adv": ad[0], "dec": ad[1], "dd30": 15, "near10": 40, "cov": 100} for i, v in enumerate(a200s)]


class TestAlerts(unittest.TestCase):
    def test_cross_fires_once_then_cooldown(self):
        r = rows([55] * 30 + [48])
        self.assertTrue(any("하향 돌파" in a for a in B.alerts("spx", r)))
        r2 = rows([55] * 30 + [48, 52, 47])   # 곧바로 다시 오가도 10거래일 안엔 다시 울리지 않는다
        self.assertEqual(B.alerts("spx", r2), [])

    def test_quiet_day_sends_nothing(self):
        self.assertEqual(B.alerts("spx", rows([55] * 40)), [])

    def test_last_session_skips_weekend(self):
        self.assertEqual(B.last_us_session(datetime(2026, 11, 30, 8, 0, tzinfo=KST)).isoformat(), "2026-11-27")   # 월요일 아침 → 금요일

    def test_code_has_no_bare_counts(self):
        c = B.code("spx", 5)
        self.assertIn('ETF="IVV"', c)
        self.assertIn("100*v/a[0]", c)   # 종목 수(503 등)는 출력하지 않는다 — 커넥터 감시 훅 오인 방지


if __name__ == "__main__":
    unittest.main()
