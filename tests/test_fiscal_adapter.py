"""Fiscal.ai 어댑터·장기 월봉 시험 (마스터 지시 2026-10-30 — easyconomics 퇴역, Fiscal.ai MCP만)"""
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

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


class TestForwardMultiples(unittest.TestCase):
    def test_put_forward_fills_target_peers_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "knowledge" / "models" / "companies" / "co-x"
            d.mkdir(parents=True)
            (d / "datapack.json").write_text(json.dumps({"multiples_now": {"ev_sales": 2.0}, "peers": [{"ticker": "AAA"}, {"ticker": "BBB"}]}), encoding="utf-8")
            out = {"as_of": "2026-10-30", "target": {"pe_fwd": 9.1, "ev_ebitda_fwd": 5.6, "src": {"pe_fwd": "fiscal"}}, "ntm": {"eps": 5.6, "ebitda": 4.0},
                   "horizons": {"2": {"eps": 7.0, "ebitda": 5.0, "ext": 0}, "3": {"eps": -1.0, "ebitda": 8.0, "ext": 2}}, "guided": {"eps": True},
                   "peers": {"NASDAQ_AAA": {"pe_fwd": 15.0, "ev_ebitda_fwd": 12.0, "ntm": {"revenue": 120.0, "ebit": 24.0, "rev_ttm": 100.0, "eps": 2.0}, "horizons": {"2": {"eps": 3.0}}}},
                   "history": [{"date": "2026-08-31", "pe_fwd": 14.4, "ev_ebitda_fwd": None}, {"date": "2026-09-30", "pe_fwd": 14.2, "ev_ebitda_fwd": 10.2}]}
            with patch.object(adapter, "ROOT", Path(tmp)):
                now, n, h = adapter.put_forward("co-x", out)
            dp = json.loads((d / "datapack.json").read_text(encoding="utf-8"))
        self.assertEqual((now["pe_fwd"], n, h), (9.1, 1, 2))
        self.assertEqual(dp["multiples_now"], {"ev_sales": 2.0, "pe_fwd": 9.1, "ev_ebitda_fwd": 5.6, "pe_fwd2": 7.28, "ev_ebitda_fwd2": 4.48, "pe_fwd3": None, "ev_ebitda_fwd3": 2.8})   # 3년 뒤 적자면 비움
        self.assertEqual(dp["peers"][0]["pe_fwd2"], 10.0)
        self.assertEqual(dp["forward"]["horizons"]["3"]["ext"], 2)
        self.assertEqual({k: dp["peers"][0][k] for k in ("pe_fwd", "ntm_ebit_margin", "ntm_growth")}, {"pe_fwd": 15.0, "ntm_ebit_margin": 0.2, "ntm_growth": 0.2})
        self.assertNotIn("pe_fwd", dp["peers"][1])
        self.assertEqual(dp["forward"]["ntm"], {"eps": 5.6, "ebitda": 4.0})
        self.assertEqual(len(dp["history"]["pe_fwd"]), 2)
        self.assertEqual(dp["history"]["ev_ebitda_fwd"], [{"date": "2026-09-30", "value": 10.2}])


if __name__ == "__main__":
    unittest.main()
