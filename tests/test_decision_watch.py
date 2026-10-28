"""3요인 지표(decision.py)·핵심 루프(alpha_watch.py) 오프라인 시험 — 마스터 지시 2026-10-28"""
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
sys.path.insert(0, str(ROOT / "radar"))

import alpha_watch  # noqa: E402
import decision  # noqa: E402

KST = timezone(timedelta(hours=9))
C = {"kelly_fraction": 0.25, "max_position": 0.10, "strong_excess": 0.05, "strong_p_beat": 0.6, "strong_mos": 0.8,
     "neutral_excess": 0.0, "neutral_p_beat": 0.5}


class TestDecision(unittest.TestCase):
    def test_kelly_binary_closed_form(self):
        # 이기면 2배(확률 0.6), 지면 절반 — 해석해 f* = 0.8
        f, _ = decision.kelly([2.0] * 6 + [0.5] * 4, rf=0.0, h=1)
        self.assertAlmostEqual(f, 0.8, places=2)

    def test_signal_tiers(self):
        self.assertEqual(decision.signal(0.06, 0.7, 0.9, C), "강함")
        self.assertEqual(decision.signal(0.01, 0.55, 0.3, C), "중립")
        self.assertEqual(decision.signal(-0.02, 0.4, 0.9, C), "약함")

    def test_budget_gated_when_below_cost_of_equity(self):
        mc = {"v0": [80.0] * 100, "vh": [120.0] * 100}   # 시총 100 → 5년 1.2배 = 연 3.7% < 자기자본비용 10%
        d = decision.compute(mc, 100.0, ke=0.10, rf=0.05, c=C)
        self.assertTrue(d["risk_budget"]["gated"])
        self.assertEqual(d["risk_budget"]["budget"], 0.0)
        self.assertEqual(d["attractiveness"]["signal"], "약함")

    def test_budget_capped_and_upside(self):
        mc = {"v0": [150.0] * 50 + [120.0] * 50, "vh": [400.0] * 50 + [150.0] * 50}
        d = decision.compute(mc, 100.0, ke=0.10, rf=0.05, c=C)
        self.assertLessEqual(d["risk_budget"]["budget"], C["max_position"])
        self.assertEqual(d["upside"]["p2"], 0.5)
        self.assertEqual(d["upside"]["p3"], 0.5)

    def test_lines_have_no_advice_words(self):
        mc = {"v0": [150.0] * 100, "vh": [300.0] * 100}
        text = "\n".join(decision.lines(decision.compute(mc, 100.0, 0.10, 0.05, C)))
        for bad in ("매수하", "매도하", "사라", "팔아라", "목표주가"):
            self.assertNotIn(bad, text)


class TestAlphaWatch(unittest.TestCase):
    CW = {"levels": ["P0", "P1"], "lookback_hours": 26, "earnings_days_after": 1, "drivers_stale_days": 45}

    def test_detect_alert_entry_earnings(self):
        now = datetime(2026, 10, 29, 9, 0, tzinfo=KST)
        st = {"last_run": "2026-10-29T08:00:00+09:00", "alpha_seen": {"co-isc": 6.2}}
        passed = {"co-isc": 6.2, "co-taihan": 5.7, "co-new": 5.1}
        alerts = {"a": {"sent_at": "2026-10-29T08:30:00+09:00", "level": "P1", "entities": ["co-isc", "co-x"], "what": "3Q 실적", "doc_type": "공시"},
                  "b": {"sent_at": "2026-10-29T07:00:00+09:00", "level": "P1", "entities": ["co-taihan"], "what": "old"},
                  "c": {"sent_at": "2026-10-29T08:40:00+09:00", "level": "P2", "entities": ["co-taihan"], "what": "p2"}}
        events = [{"id": "co-taihan", "date": "2026-10-29", "time_kst": "15:00"}, {"id": "co-isc", "date": "2026-11-20"}]
        found, p0 = alpha_watch.detect(now, st, passed, alerts, events, self.CW)
        self.assertIn("co-isc", found)                       # 새 P1 알림
        self.assertNotIn("co-x", found)                      # 알파 기준 미만
        self.assertTrue(any("실적 발표" in r for r in found["co-taihan"]))   # 실적일
        self.assertFalse(any("old" in r for r in found["co-taihan"]))       # 지난 실행 이전 알림 제외
        self.assertTrue(any("진입" in r for r in found["co-new"]))          # 새로 기준 이상
        self.assertEqual(p0, set())

    def test_first_run_no_entry_flood(self):
        now = datetime(2026, 10, 29, 9, 0, tzinfo=KST)
        found, _ = alpha_watch.detect(now, {}, {"co-a": 6.0, "co-b": 7.0}, {}, [], self.CW)
        self.assertEqual(found, {})                          # 첫 실행은 기준선만

    def test_needs_update(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "drivers.yaml"
            with mock.patch.object(alpha_watch, "drivers_path", lambda eid: p):
                self.assertEqual(alpha_watch.needs_update("co-a", [], self.CW, date(2026, 10, 29)), "작성")
                p.write_text("as_of: 2026-10-28\n", encoding="utf-8")
                self.assertIsNone(alpha_watch.needs_update("co-a", ["P1 공시: x"], self.CW, date(2026, 10, 29)))
                self.assertEqual(alpha_watch.needs_update("co-a", ["실적 발표(2026-10-29 15:00)"], self.CW, date(2026, 10, 29)), "갱신")
                self.assertEqual(alpha_watch.needs_update("co-a", [], self.CW, date(2027, 1, 30)), "갱신")   # 45일 초과


if __name__ == "__main__":
    unittest.main()
