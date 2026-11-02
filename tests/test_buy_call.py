"""Portfolio Buy Call (마스터 지시 2026-11-02)"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
import buy_call as bc  # noqa: E402
import composite  # noqa: E402

TODAY = date(2026, 11, 2)
REP = {"id": "co-x", "ticker": "XYZ", "company": "엑스", "date": "2026-11-02", "stem": "20261102_XYZ", "grade": "Buy", "target": 130.0, "target_text": "$130", "alpha": 6.5, "rr": 3.0,
       "price": 100.0, "bear": 85.0, "bull": 145.0, "dcf": 110.0, "swing": "다음 실적"}


class TestJudge(unittest.TestCase):
    def setUp(self):
        self.c, self.cfg = composite.cfg(), bc.report_layout.config()

    def judge(self, r=REP, price=100.0, alpha=6.5, killed=()):
        return bc.judge(r, price, alpha, self.c, self.cfg, TODAY, killed)

    def test_buy_with_high_alpha_passes(self):
        row, why = self.judge()
        self.assertEqual((row["grade_now"], why), ("Buy", ""))

    def test_price_run_up_removes_call(self):
        row, why = self.judge(price=120.0)
        self.assertIsNone(row)
        self.assertIn("Neutral", why)

    def test_price_fall_can_lift_grade(self):
        row, _ = self.judge(price=90.0)
        self.assertEqual(row["grade_now"], "Strong Buy")

    def test_low_alpha_fails(self):
        self.assertIn("알파", self.judge(alpha=5.0)[1])
        self.assertIn("미산정", self.judge(alpha=None)[1])

    def test_old_report_fails(self):
        self.assertIn("경과", self.judge(dict(REP, date="2026-08-01"))[1])

    def test_killed_fails(self):
        self.assertEqual(self.judge(killed=("XYZ",))[1], "킬 조건 발동")


class TestRun(unittest.TestCase):
    def run_it(self, px, prev):
        return bc.run(TODAY, px=px, reps={"co-x": REP}, alphas={"co-x": {"total": 6.5}}, prev=prev)

    def test_new_entry_is_flagged(self):
        out = self.run_it({"XYZ": 100.0}, {})
        self.assertTrue(out["calls"]["co-x"]["new"])
        t = bc.text(out)
        self.assertIn("🆕 엑스(XYZ) **Buy** · 목표주가 $130 · 업사이드 +30% · 손익비 3.0 · 알파 6.5", t)
        self.assertIn("가를 것: 다음 실적", t)
        self.assertIn("매매·비중·금액 지시가 아님", t)

    def test_drop_says_why(self):
        prev = self.run_it({"XYZ": 100.0}, {})["calls"]
        out = self.run_it({"XYZ": 120.0}, prev)
        self.assertEqual(out["calls"], {})
        self.assertIn("해제 엑스(XYZ)", bc.text(out))

    def test_nothing_says_nothing(self):
        self.assertEqual(bc.text(bc.run(TODAY, px={}, reps={}, alphas={}, prev={})), "")

    def test_missing_price_is_marked(self):
        self.assertIn("시세 미갱신", bc.text(self.run_it({}, {})))

    def test_log_records_entry_and_exit(self):
        prev = self.run_it({"XYZ": 100.0}, {})
        out = self.run_it({"XYZ": 120.0}, prev["calls"])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "log.csv"
            bc.record(prev, p)
            bc.record(out, p)
            self.assertEqual([x.split(",")[1] for x in p.read_text(encoding="utf-8").splitlines()[1:]], ["진입", "해제"])


class TestScenario(unittest.TestCase):
    def test_new_reports_store_it(self):
        self.assertEqual(bc.scenario({"verdict": {"price": 100, "bear": 80, "bull": 150, "dcf_up": 0.1}})[3], 110.00000000000001)

    def test_old_reports_are_rebuilt(self):
        d = {"verdict": {"downside": -0.1, "rr": 3.0}, "tiles": [{"k": "주가", "v": "$1,000.50"}], "x": "DCF 기준 업사이드는 기본 −43%, 강세"}
        p, bear, bull, dcf = bc.scenario(d)
        self.assertEqual(p, 1000.5)
        self.assertAlmostEqual(bear, 900.45)
        self.assertAlmostEqual(bull, 1300.65)
        self.assertAlmostEqual(dcf, 570.285)


class TestComposite(unittest.TestCase):
    def test_report_rr_replaces_asymmetry(self):
        c = composite.cfg()
        alpha = {"total": 8.0, "components": {"asymmetry": 2.0}}
        self.assertEqual(composite.score({"tv": {}}, alpha, c, {"rr": 3.5})["reward_risk"], 10.0)
        self.assertEqual(composite.score({"tv": {}}, alpha, c)["reward_risk"], 2.5)

    def test_screener_row_gets_id(self):
        self.assertEqual(composite.resolve_id({"ticker": "NASDAQ:UCTT"}, {"UCTT": "co-ultraclean"}), "co-ultraclean")
        self.assertEqual(composite.resolve_id({"ticker": "NYSE:ABC"}, {}), "us-abc")
        self.assertIsNone(composite.resolve_id({"ticker": "TSE:6857"}, {}))

    def test_high_technical_goes_to_alpha_queue(self):
        strong = {"close": 100, "SMA50": 90, "SMA200": 80, "RSI": 60, "relative_volume_10d_calc": 1.5, "Perf.1M": 5, "Perf.3M": 10, "price_52_week_high": 105}
        sent = []
        with mock.patch.object(composite, "alpha_rows", lambda: {}), mock.patch.object(composite, "tv_ids", lambda: {}), mock.patch.object(bc, "reports", lambda: {}), \
                mock.patch("alpha_watch.enqueue", lambda *a: sent.append(a)):
            composite.run({"rows": [{"ticker": "NYSE:ABC", "name": "A", "tv": strong}]})
        self.assertEqual((sent[0][0], sent[0][3]), ("us-abc", "알파 산정"))


class TestPrune(unittest.TestCase):
    def test_drops_rows_with_fresh_drivers(self):
        import alpha_watch as aw
        with tempfile.TemporaryDirectory() as d:
            q = Path(d) / "q.json"
            q.write_text(json.dumps([{"id": "a", "kind": "작성"}, {"id": "b", "kind": "작성"}, {"id": "c", "kind": "알파 산정"}]), encoding="utf-8")
            with mock.patch.object(aw, "QUEUE", q), mock.patch.object(aw, "needs_update", lambda e, r, c, t: None if e == "a" else "작성"):
                self.assertEqual(aw.prune({}, TODAY), (2, 1))
            self.assertEqual([x["id"] for x in json.loads(q.read_text(encoding="utf-8"))], ["b", "c"])


if __name__ == "__main__":
    unittest.main()
