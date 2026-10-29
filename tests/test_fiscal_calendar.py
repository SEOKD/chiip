"""어닝 캘린더 Fiscal.ai 전환 시험 (마스터 지시 2026-10-30 "어닝캘린더도 Fiscal.ai를 참조하라")"""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))

from markets import earnings_calendar as ec  # noqa: E402
from pollers import common  # noqa: E402

WL = [{"id": "co-quanta-services", "name": "Quanta", "code": "PWR.US", "region": "US"},
      {"id": "co-nvidia", "name": "NVIDIA", "code": "NVDA.US", "region": "US"},
      {"id": "co-primoris", "name": "Primoris", "code": "PRIM.US", "region": "US"},
      {"id": "co-samsung", "name": "삼성전자", "code": "005930.KO", "region": "KR"},
      {"id": "co-hanmisemi", "name": "한미반도체", "code": "042700.KO", "region": "KR"},
      {"id": "co-tsmc", "name": "TSMC", "code": "2330.TW", "region": "TW"},
      {"id": "co-tel", "name": "Tokyo Electron", "code": None, "region": "JP"},
      {"id": "co-rollsroyce", "name": "Rolls-Royce", "code": "RR.LSE", "region": "UK"},
      {"id": "co-ibiden", "name": "Ibiden", "code": None, "region": "JP"}]
KEYS = {"keys": {"co-quanta-services": {"key": "NYSE_PWR"}, "co-tsmc": {"key": "NYSE_TSM"}, "co-tel": {"key": "XJPX_8035"}}}


def ev(key, d, status="confirmed", session="after_close", utc=None, roles=("financial_results_release",), q="key", ticker=None):
    return {"key": key, "ticker": ticker or key.split("_", 1)[1], "date": d, "status": status, "session": session, "utc": utc,
            "period": "Q3 2026", "window": None, "q": q, "roles": list(roles)}


DATA = {"events": [
    ev("NYSE_PWR", "2026-10-29", session="before_open", utc="2026-10-29T13:00:00Z", roles=("financial_results_release", "earnings_call_for_results")),
    ev("NASDAQ_NVDA", "2026-11-17", q="us", ticker="NVDA"),
    ev("NYSE_PRIM", "2026-11-03", q="us", ticker="PRIM"),
    ev("NYSE_PRIM", "2026-11-04", session="during_market", roles=("earnings_call_for_results",), q="us", ticker="PRIM"),
    ev("XKRX_042700", "2026-10-30", status="estimated", session=None),
    ev("XKRX_005930", "2026-10-29", status="reported", session="during_market", utc="2026-10-29T01:00:00Z"),
    ev("XJPX_8035", "2026-10-30", status="estimated", utc="2026-10-30T07:00:00Z"),
    ev("XLON_RR.", "2026-11-12"),
    ev("NASDAQ_ZZZZ", "2026-11-01", q="us", ticker="ZZZZ"),
]}


class TestFiscalCalendar(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(common, "load_yaml", lambda path: KEYS if "fiscal_keys" in path else {})
        p.start()
        self.addCleanup(p.stop)

    def test_targets(self):
        us, keys = ec.fiscal_targets(WL)
        self.assertEqual(us, {"NVDA": "co-nvidia", "PRIM": "co-primoris"})   # PWR는 캐시 키가 우선
        self.assertEqual(keys["NYSE_PWR"], "co-quanta-services")
        self.assertEqual(keys["NYSE_TSM"], "co-tsmc")          # XTAI_2330 대신 1차 상장 키
        self.assertEqual(keys["XKRX_005930"], "co-samsung")
        self.assertEqual(keys["XLON_RR"], "co-rollsroyce")
        self.assertNotIn("co-ibiden", keys.values())           # 코드·캐시 키 없으면 묻지 않는다

    def test_events(self):
        out = {(e["id"], e["date"]): e for e in ec.fiscal_events(WL, DATA)}
        pwr = out[("co-quanta-services", "2026-10-29")]
        self.assertEqual((pwr["time_kst"], pwr["local"], pwr["status"], pwr["source"], pwr["url"]), ("22:00", "장전", "확정", "Fiscal.ai", ""))
        self.assertIn("콜", pwr["title"])
        self.assertIn(("co-rollsroyce", "2026-11-12"), out)    # 'XLON_RR.' 점 붙은 키
        self.assertIn(("co-tel", "2026-10-30"), out)
        self.assertNotIn(("co-primoris", "2026-11-04"), out)   # 발표 다음 날 콜은 발표 행 하나로
        self.assertIn(("co-primoris", "2026-11-03"), out)
        self.assertEqual(len([e for e in out.values() if e["name"] == "ZZZZ"]), 0)

    def test_merge_prefers_kind_for_korea(self):
        fiscal = ec.fiscal_events(WL, DATA)
        kind = [{"id": "co-hanmisemi", "name": "한미반도체", "date": "2026-11-03", "time_kst": "16:00", "local": "", "title": "실적발표",
                 "source": "KIND IR일정", "url": ""},
                {"id": "co-samsung", "name": "삼성전자", "date": "2026-10-29", "time_kst": "", "local": "", "title": "실적발표",
                 "source": "KIND IR일정", "url": ""}]
        out = {(e["id"], e["date"]): e for e in ec.merge(fiscal, kind)}
        self.assertNotIn(("co-hanmisemi", "2026-10-30"), out)   # KIND 일정이 있으면 Fiscal 추정 일정은 버림
        self.assertEqual(out[("co-hanmisemi", "2026-11-03")]["source"], "KIND IR일정")
        self.assertEqual(out[("co-samsung", "2026-10-29")]["source"], "Fiscal.ai")   # 같은 날은 시각 있는 쪽

    def test_code_and_put(self):
        code = ec.fiscal_code(WL, date(2026, 10, 30), 21)
        self.assertNotIn("__", code)
        self.assertIn('"2026-10-29"', code)
        self.assertIn('"XLON_RR"', code)
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / "out.txt"
            raw.write_text("로그\n" + json.dumps(DATA), encoding="utf-8")
            with mock.patch.object(ec, "FISCAL", Path(d) / "fiscal.json"):
                data = ec.fiscal_put(raw)
                self.assertEqual(len(data["events"]), len(DATA["events"]))
                self.assertLess(ec.fiscal_age(), 1)
                self.assertEqual(len(ec.fiscal_events(WL)), 7)

    def test_due(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(ec, "FISCAL", Path(d) / "fiscal.json"):
            now = datetime(2026, 10, 31, 6, 35, tzinfo=common.KST)
            self.assertTrue(ec.fiscal_due(now))                                   # 파일 없음
            self.assertFalse(ec.fiscal_due(datetime(2026, 10, 31, 4, 35, tzinfo=common.KST)))   # 05시 전
            ec.FISCAL.write_text(json.dumps({"fetched": "2026-10-31T05:35:00+09:00", "events": []}), encoding="utf-8")
            self.assertFalse(ec.fiscal_due(now))                                  # 오늘 05시 이후 받음
            ec.FISCAL.write_text(json.dumps({"fetched": "2026-10-30T23:35:00+09:00", "events": []}), encoding="utf-8")
            self.assertTrue(ec.fiscal_due(now))                                   # 어제 받음


if __name__ == "__main__":
    unittest.main()
