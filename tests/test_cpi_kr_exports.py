"""CPI·한국 반도체 수출 수집기(마스터 지시 2026-11-13) — 발표 창·요약·개정·fail-closed"""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import cpi_release as cr  # noqa: E402
import kr_exports as ke  # noqa: E402
from pollers import common  # noqa: E402

MOTIE = ("【 총괄 】 '26.10 월 수출은 전년 동월 대비 93.7% 증가한 1,152.8 억 달러 , 수입은 36.0% 증가한 727.8 억 달러 . "
         "조업일수를 고려한 일평균 수출은 76% 증가한 52.4 억 달러로 2 개월 연속. 【 10 월 20 대 주요품목별 수출액 ( 억 달러 ) 및 증감률 (%) 】 "
         "반도체 디스플레이 무선통신기기 컴퓨터 자동차 자동차부품 선박 564 (+259) 19 (+29) 19 (+7) 59 (+497) 65 (+18) 17 (+15) 26 ( △ 44) "
         "컴퓨터 (58.5 억 달러 , +496.6%) 수출은 서버 인프라 투자 확대 , 선박 (26.4 억 달러 , △ 43.6%) 수출은")


class TestCpi(unittest.TestCase):
    def setUp(self):
        self.p = mock.patch.object(cr, "OUT", Path(tempfile.mkdtemp()) / "cpi.json")
        self.p.start()

    def tearDown(self):
        self.p.stop()

    def test_calendar_and_window(self):
        self.assertIn(date(2026, 12, 10), cr.pr.releases("BLS CPI"))
        with mock.patch.object(cr.pr, "releases", lambda e: [date(2026, 12, 10)]):
            self.assertEqual(cr.window(datetime(2026, 12, 10, 22, 41, tzinfo=common.KST)), date(2026, 12, 10))
            self.assertIsNone(cr.window(datetime(2026, 12, 10, 22, 0, tzinfo=common.KST)))

    def test_update_summary_and_revision(self):
        raw = {s: {"2025-09": 100.0, "2026-08": 102.0, "2026-09": 103.0} for pair in cr.SERIES.values() for s in pair}
        cr.update(datetime(2026, 11, 1, tzinfo=common.KST), fetch=lambda ids: raw)
        raw2 = {s: {**v, "2026-09": 103.1, "2026-10": 103.5} for s, v in raw.items()}
        month, revs, text = cr.update(datetime(2026, 12, 10, 22, 45, tzinfo=common.KST), fetch=lambda ids: raw2)
        self.assertEqual(month, "2026-10")
        self.assertTrue(revs and revs[0]["old"] == 103.0)
        self.assertIn("헤드라인은 전월 대비 +0.4%", text)
        self.assertIn("전년 같은 달 값이 없어", text)   # 2025-10 없음 — 지어내지 않는다
        self.assertIn("개정", text)

    def test_fail_closed(self):
        with mock.patch.object(cr, "window", lambda now: date(2026, 12, 10)), mock.patch.object(cr, "update", side_effect=RuntimeError("BLS down")), \
             mock.patch.object(common, "save_state"), mock.patch.object(common, "record_health"), mock.patch.object(common, "save_new_items") as sv, \
             mock.patch.object(common, "load_state", lambda n, d=None: {}):
            self.assertIn("수집 실패", cr.run(datetime(2026, 12, 10, 22, 45, tzinfo=common.KST)))
            sv.assert_not_called()


class TestKrExports(unittest.TestCase):
    def test_parse_release(self):
        r = ke.parse(MOTIE)
        self.assertEqual(r["total"], {"usd_100m": 1152.8, "yoy": 0.937})
        self.assertEqual(r["daily_avg"]["usd_100m"], 52.4)
        self.assertEqual((r["반도체"]["usd_100m"], round(r["반도체"]["yoy"], 2)), (564.0, 2.59))
        self.assertAlmostEqual(r["컴퓨터"]["yoy"], 4.966)
        text = ke.summary("2026-10", r)
        self.assertIn("반도체 수출은 $56.40B로 전년 대비 +259.0%", text)
        self.assertIn("일평균 $5.24B", text)

    def test_fail_closed_without_semis(self):
        d = Path(tempfile.mkdtemp())
        with mock.patch.object(ke, "OUT", d / "k.json"), mock.patch.object(ke, "latest_posts", lambda: [{"id": "1", "title": "2026년 10월 수출입 동향", "month": "2026-10", "url": "u"}]), \
             mock.patch.object(common, "http_get", lambda *a, **k: "<p>수출 증가</p>".encode()):
            with self.assertRaises(RuntimeError):
                ke.collect(datetime(2026, 11, 1, 10, tzinfo=common.KST))
            doc = json.loads((d / "k.json").read_text(encoding="utf-8"))
            self.assertEqual(doc["releases"], {})
            self.assertIn("읽지 못함", doc["gaps"][-1]["why"])

    def test_window(self):
        self.assertEqual(ke.run(datetime(2026, 11, 15, 10, tzinfo=common.KST)), "발표 창 아님")


if __name__ == "__main__":
    unittest.main()
