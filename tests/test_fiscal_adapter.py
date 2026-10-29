"""Fiscal.ai 어댑터·장기 월봉 시험 (마스터 지시 2026-10-30 — easyconomics 퇴역, Fiscal.ai MCP만)"""
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fiscal"))
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))

import adapter  # noqa: E402
import flow  # noqa: E402
import levels  # noqa: E402

OUT = {"key": "NYSE_PWR", "as_of": "2026-10-29", "currency": "USD", "mcap": 97085804838, "ev_sales": 2.745, "rev_ttm": 37288609000,
       "rev_growth": 0.371, "op_margin": 0.068, "n_analysts": 28, "price": 644.33, "ma50": 633.9, "ma200": 626.3, "high_52w": 785.24,
       "low_52w": 413.17, "eps_fwd": 19.9, "eps_ttm": 16.14, "surprises": [20.1, None, None, None], "target_mean": 795.6,
       "sector": "Industrials", "industry": "Construction & Engineering", "terminalUrl": "https://fiscal.ai/company/NYSE-PWR"}


def prices_text(n_daily=130, n_month=70):
    d0 = date(2026, 4, 1)
    daily = [f"{(d0 + timedelta(days=i)).isoformat()},{100 + i * 0.5},{101 + i * 0.5},{99 + i * 0.5},{100.5 + i * 0.5},1000" for i in range(n_daily)]
    monthly = [f"{2020 + i // 12}-{i % 12 + 1:02d}-28,{50 + i},{55 + i},{45 + i},{52 + i},20000" for i in range(n_month)]
    return "#daily\ndate,o,h,l,c,v\n" + "\n".join(daily) + "\n#monthly\ndate,o,h,l,c,v\n" + "\n".join(monthly)


class TestFiscalAdapter(unittest.TestCase):
    def test_fund_row_schema(self):
        r = adapter.fund_row(OUT)
        for k in ("mcap_usd", "rev_growth", "op_margin", "ev_sales", "n_analysts", "price", "ma50", "ma200", "high_52w", "low_52w", "eps_fwd", "eps_ttm", "surprises"):
            self.assertIn(k, r)
        self.assertEqual(r["mcap_usd"], OUT["mcap"])
        self.assertIn("Fiscal.ai", r["source"])
        self.assertIsNone(adapter.fund_row({**OUT, "currency": "JPY"})["mcap_usd"])   # 달러가 아니면 환산 전까지 비운다

    def test_split_prices(self):
        d, m = adapter.split_prices(prices_text(5, 3))
        self.assertEqual(len(d), 6)
        self.assertEqual(len(m), 4)
        self.assertEqual(d[0], "date,o,h,l,c,v")

    def test_ohlcv_files_and_long_monthly(self):
        with tempfile.TemporaryDirectory() as t:
            saved = (adapter.ROOT, flow.ROOT)
            adapter.ROOT = flow.ROOT = Path(t)
            try:
                n, m = adapter.put_ohlcv("x-test", prices_text())
                self.assertEqual((n, m), (130, 70))
                self.assertTrue(flow.approx_hl("x-test"))
                daily, monthly = flow.load_ohlcv("x-test"), flow.load_monthly("x-test")
                self.assertEqual(len(daily), 130)
                merged = levels.merge_monthly(monthly, daily)
                self.assertGreater(len(merged), 60)   # 장기 월봉 + 최근 일봉 월봉
                self.assertEqual(len({b["date"][:7] for b in merged}), len(merged))   # 같은 달 중복 없음
                sw = levels.dominant(merged, "월봉")
                self.assertIn("60개월", sw["basis"])
                sec = levels.report_section("x-test", {})
                self.assertIsNotNone(sec)
                self.assertIn("근사", sec["blocks"][-1]["text"])
            finally:
                adapter.ROOT, flow.ROOT = saved

    def test_key_cache(self):
        self.assertEqual(adapter.key_of("co-quanta-services"), "NYSE_PWR")


if __name__ == "__main__":
    unittest.main()
