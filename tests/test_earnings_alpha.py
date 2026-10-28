"""어닝 캘린더·알파 잠재력 점수·인사이트 검토 상태(§21.15) 오프라인 테스트"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "radar" / "markets"))
sys.path.insert(0, str(ROOT / "scripts"))

import earnings_calendar as ec  # noqa: E402
import insight_state  # noqa: E402
alpha = ec._alpha()  # scripts/alpha/score.py (포커스 score.py와 이름 충돌 방지)

KIND_HTML = """
<table><tbody>
<tr><td>3</td><td><a href="#" onclick="fnPopupIRInfoDetail('901');">삼성전자</a></td>
<td>2026년 3분기 경영실적 발표</td><td>-</td><td>2026-10-29</td><td>10:00</td></tr>
<tr><td>2</td><td><a href="#" onclick="fnPopupIRInfoDetail('902');">삼성전자</a></td>
<td>Announce 3Q 2026 results</td><td>-</td><td>2026-10-29</td><td>10:00</td></tr>
<tr><td>1</td><td><a href="#" onclick="fnPopupIRInfoDetail('903');">ISC</a></td>
<td>2026년 3분기 경영실적 및 경영현황 설명</td><td>서울 여의도</td><td>2026-10-29</td><td>--:--</td></tr>
<tr><td>0</td><td><a href="#" onclick="fnPopupIRInfoDetail('904');">ISC</a></td>
<td>Q3 2026 Earnings Release</td><td>Online</td><td>2026-10-29</td><td>09:00</td></tr>
<tr><td>9</td><td>휴메딕스</td><td>투자자 이해증진</td><td>서울</td><td>2026-10-29</td><td>09:00</td></tr>
<tr><td colspan="6">헤더 아닌 행</td></tr>
</tbody></table>
"""
WL = [{"id": "co-samsung", "name": "삼성전자", "kind_name": "삼성전자", "code": "005930.KO", "region": "KR"},
      {"id": "co-isc", "name": "ISC", "kind_name": "ISC", "code": "095340.KQ", "region": "KR"}]


class TestKind(unittest.TestCase):
    def test_parse_and_dedupe(self):
        rows = ec.parse_kind(KIND_HTML)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["ir_seq"], "901")
        ev = {e["id"]: e for e in ec.kind_events(rows, WL)}
        self.assertEqual(len(ev), 2)                       # 국문·영문 중복 → 1건, 감시 목록 밖(휴메딕스) 제외
        self.assertEqual(ev["co-isc"]["time_kst"], "09:00")  # 시각 미정(--:--)보다 시각 있는 공시 우선
        self.assertIn("irSeq=", ev["co-samsung"]["url"])


class TestDigest(unittest.TestCase):
    def test_only_alpha_pass(self):
        events = [{"id": "co-isc", "name": "ISC", "date": "2026-10-29", "time_kst": "09:00", "local": "", "title": "t", "source": "KIND", "url": ""},
                  {"id": "co-samsung", "name": "삼성전자", "date": "2026-10-29", "time_kst": "10:00", "local": "", "title": "t", "source": "KIND", "url": ""},
                  {"id": "co-x", "name": "X", "date": "2026-10-30", "time_kst": "", "local": "", "title": "t", "source": "KIND", "url": ""},
                  {"id": "co-isc", "name": "ISC", "date": "2026-11-20", "time_kst": "", "local": "", "title": "t", "source": "KIND", "url": ""}]
        rows = {"co-isc": {"total": 6.2}, "co-samsung": {"total": 4.9}}
        with mock.patch.object(alpha, "load_latest", return_value=({"co-isc": 6.2}, rows)):
            text = ec.digest(events, 2, date(2026, 10, 29))
        self.assertIn("ISC — 알파 6.2", text)
        self.assertNotIn("삼성전자", text)                  # 기준 미달은 이름도 안 보냄
        self.assertIn("기준 미달 1·미산정 1", text)
        self.assertIn("투자 권유가 아님", text)
        with mock.patch.object(alpha, "load_latest", return_value=({}, rows)):
            self.assertIsNone(ec.digest(events, 2, date(2026, 10, 29)))   # 통과 종목 없으면 발송 안 함


class TestAlpha(unittest.TestCase):
    CFG = {"weights": {"upside": 0.3, "gap": 0.3, "bottleneck": 0.2, "asymmetry": 0.2}, "min_components": 2,
           "threshold": 5.0, "stale_days": 14}

    def test_combine_renormalize_and_min(self):
        j = {"a": {"upside": {"score": 8, "day": "20261028"}, "bottleneck": {"score": 6, "day": "20261027"}},
             "b": {"gap": {"score": 9, "day": "20261028"}}}
        r = alpha.combine(j, self.CFG)
        self.assertAlmostEqual(r["a"]["total"], (0.3 * 8 + 0.2 * 6) / 0.5, places=2)
        self.assertEqual(r["a"]["scored_on"], "20261028")
        self.assertIsNone(r["b"]["total"])                    # 요소 1개 → 미산정

    def test_load_latest_stale(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "latest.json"
            p.write_text(json.dumps({"rows": {"a": {"total": 6.0, "scored_on": "20261028"},
                                              "old": {"total": 8.0, "scored_on": "20260901"},
                                              "low": {"total": 4.0, "scored_on": "20261028"}}}), encoding="utf-8")
            with mock.patch.object(alpha, "LATEST", p), mock.patch.object(alpha, "cfg", return_value=self.CFG):
                passed, rows = alpha.load_latest(date(2026, 10, 29))
        self.assertEqual(passed, {"a": 6.0})                  # 오래된 점수·기준 미달 제외
        self.assertEqual(len(rows), 3)


class TestInsightState(unittest.TestCase):
    def test_check_mark(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(insight_state, "STATE", Path(d) / "s.json"):
            pid = "407b5d1e-0998-8074-842f-ea2b3259f64a"
            self.assertEqual(insight_state.check(pid, "2026-10-28T09:57:00Z"), "DUE")
            insight_state.mark(pid, "2026-10-28T10:30:00Z", "https://notion/x")
            self.assertEqual(insight_state.check(pid, "2026-10-28T10:30:00Z"), "SKIP")
            self.assertEqual(insight_state.check(pid.replace("-", ""), "2026-10-29T01:00:00+00:00"), "DUE")


if __name__ == "__main__":
    unittest.main()
