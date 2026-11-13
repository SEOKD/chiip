"""Pulse 점검(2026-11-14 마스터 지시 "Pulse의 역량을 조금 더 끌어올려봐. 시스템 전반을 점검해") — 채용 공고 잡음·실적 접수 시각·앱 예약 정지"""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import pulse  # noqa: E402
import pulse_trigger as pt  # noqa: E402
from pollers import common  # noqa: E402


class TestJobPosts(unittest.TestCase):
    def test_job_titles_dropped(self):
        for t in ("Mission Engineer in Sterling, Virginia, United States | Intelligence at BAE Systems - BAE Systems",
                  "General Maintenance Worker - Norfolk, VA, US - RQ212310 - General Dynamics",
                  "[IR] EU:SAAB-B: Head of Business Unit Procurement - Saab",
                  "Compass Call Flight Line and Backshop FSR - BAE Systems"):
            self.assertTrue(pulse.is_job_post({"title": t}), t)

    def test_news_kept(self):
        for t in ("BAE Systems accelerates delivery of advanced LRASM missile sensors - BAE Systems",
                  "BAE Systems names new Chief Engineer",
                  "Lockheed awarded $2B contract for F-35 engineers",
                  "[IR] EU:IFX: Infineon Investor Presentation - Infineon Technologies",
                  "NRC Issues First Construction Permit in Nearly 60 Years for High-Temperature Reactor"):
            self.assertFalse(pulse.is_job_post({"title": t}), t)

    def test_career_url(self):
        self.assertTrue(pulse.is_job_post({"title": "Software Team", "url": "https://careers.example.com/x"}))


class TestEarningsAtom(unittest.TestCase):
    def test_et_to_kst_dst(self):
        self.assertEqual(pulse.et_to_kst("20261110160158"), "2026-11-11T06:01+09:00")   # EST(UTC−5)
        self.assertEqual(pulse.et_to_kst("20260701120000"), "2026-07-02T01:00+09:00")   # EDT(UTC−4)
        self.assertEqual(pulse.et_to_kst("20261101010000"), "2026-11-01T14:00+09:00")   # 서머타임 끝나기 전(02시)

    def test_atom_picks_only_universe_earnings(self):
        atom = ('<entry><title>8-K - Vuzix Corp (0001463972) (Filer)</title><link href="https://www.sec.gov/Archives/edgar/data/1463972/000146397226000050/0001463972-26-000050-index.htm"/></entry>'
                '<entry><title>8-K - Other (0000000001) (Filer)</title><link href="https://www.sec.gov/Archives/edgar/data/1/000000000126000001/0000000001-26-000001-index.htm"/></entry>')
        head = "<ACCEPTANCE-DATETIME>20261113163012\nCOMPANY CONFORMED NAME:\tVuzix Corp\nITEM INFORMATION:\tResults of Operations and Financial Condition\n"
        calls = []

        def fake(url, params=None, headers=None, timeout=20):
            calls.append(url)
            if "browse-edgar" in url:
                return atom.encode() if params.get("start") == 0 else b""
            return head.encode()
        st = {"cik_tk": {"1463972": "VUZI", "1": "OTHR"}, "cik_tk_day": common.now_kst().date().isoformat()}
        with mock.patch.object(common, "http_get", fake), mock.patch.object(pulse.time, "sleep", lambda s: None):
            seen = set()
            out = pulse.atom_earnings({"VUZI": "us-vuzix"}, seen, st)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["published_at"], "2026-11-14T06:30+09:00")
        self.assertIn("0001463972-26-000050", seen)
        self.assertFalse(any("0000000001" in c for c in calls if "index-headers" in c))   # 감시 밖은 열지 않는다


class TestAppStall(unittest.TestCase):
    def rows(self, *ts_via):
        return [{"kind": "gate", "task": "chiip-pulse", "ts": t, **({"via": v} if v else {})} for t, v in ts_via]

    def test_stall_ignores_trigger_rows(self):
        c = {"stall_min": {"weekday": 20, "weekend": 90}}
        now = datetime(2026, 11, 10, 9, 0, tzinfo=common.KST)   # 월요일
        rows = self.rows(("2026-11-10T07:30:39+09:00", None), ("2026-11-10T08:50:00+09:00", "trigger"), ("2026-11-10T08:55:00+09:00", "trigger-model"))
        with mock.patch.object(pt.run_ledger, "rows", lambda d: rows):
            self.assertEqual(pt.app_stalled(c, now), "2026-11-10T07:30:39+09:00")

    def test_no_stall_when_app_recent_or_weekend_window(self):
        c = {"stall_min": {"weekday": 20, "weekend": 90}}
        with mock.patch.object(pt.run_ledger, "rows", lambda d: self.rows(("2026-11-10T08:50:00+09:00", None))):
            self.assertIsNone(pt.app_stalled(c, datetime(2026, 11, 10, 9, 0, tzinfo=common.KST)))
        with mock.patch.object(pt.run_ledger, "rows", lambda d: self.rows(("2026-11-14T08:00:00+09:00", None))):   # 토요일 1시간 주기
            self.assertIsNone(pt.app_stalled(c, datetime(2026, 11, 14, 9, 10, tzinfo=common.KST)))
        self.assertIsNone(pt.app_stalled({}, datetime(2026, 11, 10, 9, 0, tzinfo=common.KST)))


if __name__ == "__main__":
    unittest.main()
