"""시세·일봉 대체 라우터·커넥터 장애 훅(마스터 지시 2026-11-22 "TradingView, Fiscal.ai 등 커넥터가 막힐 경우 다른 대안으로 이를 쓰도록 하는 시스템")"""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / ".claude" / "hooks"))
from pollers import common  # noqa: E402
import market_data as M  # noqa: E402
import connector_watch as W  # noqa: E402


class Router(unittest.TestCase):
    def setUp(self):
        self.mem = {}
        mock.patch.object(common, "load_state", side_effect=lambda n, d=None: self.mem.get(n, d)).start()
        mock.patch.object(common, "save_state", side_effect=lambda n, v: self.mem.__setitem__(n, v)).start()

    def tearDown(self):
        mock.patch.stopall()

    def test_next_source_fills_only_missing(self):
        calls = []

        def a(key, syms):
            calls.append(("tiingo", list(syms)))
            return {"AMEX:SPY": {"price": 1}}, 1

        def b(key, syms):
            calls.append(("twelvedata", list(syms)))
            return {s: {"price": 2} for s in syms}, len(syms)
        q, why = M.quote(["AMEX:SPY", "NASDAQ:NVDA"], {"TIINGO_API_KEY": "k", "TWELVEDATA_API_KEY": "k"}, {"tiingo": a, "twelvedata": b, "eodhd": b})
        self.assertEqual(q["AMEX:SPY"]["price"], 1)
        self.assertEqual(q["NASDAQ:NVDA"]["price"], 2)
        self.assertEqual(calls[1], ("twelvedata", ["NASDAQ:NVDA"]))
        self.assertEqual(why.get("eodhd"), "키 없음") if "eodhd" in why else None

    def test_http_limit_turns_source_off_for_the_day(self):
        import urllib.error

        def bad(key, syms):
            raise urllib.error.HTTPError("u", 429, "x", {}, None)
        q, why = M.quote(["AMEX:SPY"], {"TIINGO_API_KEY": "k"}, {"tiingo": bad, "twelvedata": bad, "eodhd": bad})
        self.assertEqual(q, {})
        self.assertEqual(why["tiingo"], "HTTP 429")
        q, why = M.quote(["AMEX:SPY"], {"TIINGO_API_KEY": "k"}, {"tiingo": bad, "twelvedata": bad, "eodhd": bad})
        self.assertEqual(why["tiingo"], "오늘 상한·막힘")

    def test_symbol_forms(self):
        self.assertEqual(M.split("NASDAQ:NVDA"), ("NASDAQ", "NVDA"))
        self.assertEqual(M.split("RR.LSE"), ("LSE", "RR"))
        self.assertTrue(M.is_us("NVDA") and not M.is_us("LSE:RR."))
        self.assertEqual(M._eod_code("LSE:RR."), "RR.LSE")

    def test_tiingo_parse(self):
        got, n = M.tiingo_quote("k", ["AMEX:SPY", "LSE:RR."], get=lambda u: [{"ticker": "SPY", "tngoLast": 99.0, "prevClose": 100.0, "timestamp": "t"}])
        self.assertEqual((n, got["AMEX:SPY"]["change_pct"]), (1, -1.0))
        self.assertNotIn("LSE:RR.", got)


class Hook(unittest.TestCase):
    def run_hook(self, payload, event="post"):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(W, "ROOT", Path(d)), \
                mock.patch("sys.stdin", io.StringIO(json.dumps(payload))), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            W.main(event)
            f = Path(d) / "radar" / "state" / "channel_down.json"
            return out.getvalue(), (json.loads(f.read_text(encoding="utf-8")) if f.exists() else {})

    def test_rate_limit_marks_down_and_points_to_fallback(self):
        out, st = self.run_hook({"tool_name": "mcp__easyconomics__etf_list", "tool_response": {"error": "429 Too Many Requests"}})
        self.assertIn("easyconomics", st)
        self.assertIn("market_data", out)

    def test_normal_response_ignored(self):
        out, st = self.run_hook({"tool_name": "mcp__easyconomics__etf_list", "tool_response": {"data": {"rows": [{"price": 401.2}]}, "error": None}})
        self.assertEqual((out, st), ("", {}))

    def test_failure_event_marks_fiscal(self):
        out, st = self.run_hook({"tool_name": "mcp__4056a804-908b-4b7a-b720-ace3a2bcabc9__execute_code", "error": "boom"}, "failure")
        self.assertIn("fiscal", st)

    def test_other_tools_ignored(self):
        out, st = self.run_hook({"tool_name": "Bash", "tool_response": "429"})
        self.assertEqual(st, {})


if __name__ == "__main__":
    unittest.main()
