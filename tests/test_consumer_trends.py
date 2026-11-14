"""소비재 트렌드 A단계(2026-11-14 설계안 knowledge/methods/consumer_trends_design.md) 오프라인 시험
— 애플 앱 id → 개발사 id, 위키 옛 제목 합산, 소비재 품목 나라별 수입"""
import csv
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import consumer_attention as ca  # noqa: E402
import trade_hs as th  # noqa: E402


class TestAppleResolve(unittest.TestCase):
    def test_app_id_to_artist(self):
        calls = []

        def fake(url, *a, **k):
            calls.append(url)
            return {"results": [{"trackId": 111, "artistId": 9}, {"trackId": 222, "artistId": 8}]}
        cache = {"333": "7"}
        with mock.patch.object(ca, "_get_json", fake), mock.patch.object(ca.time, "sleep", lambda s: None):
            got = ca.resolve_artists(["111", "222", "333", "111"], "ua", cache)
        self.assertEqual(got, ["9", "8", "7", "9"])
        self.assertEqual(len(calls), 1)            # 캐시에 있는 앱은 다시 묻지 않는다
        self.assertNotIn("333", calls[0])


class TestWikiMerge(unittest.TestCase):
    def test_old_title_added(self):
        tmp = Path(tempfile.mkdtemp())
        cfg = {"companies": [{"id": "x", "wiki": {"en": "New"}, "wiki_old": {"en": ["Old"]}}]}
        with mock.patch.object(ca, "WIKI_DB", tmp / "w.sqlite"), mock.patch.object(ca, "WIKI_MONTHLY", tmp / "m.csv"), \
                mock.patch.object(ca, "cfg", lambda: cfg):
            ca.wiki_store("en", "Old", {"20200101": 10, "20200102": 5, "20210101": 1})
            ca.wiki_store("en", "New", {"20210101": 100})
            ca.wiki_monthly()
            rows = list(csv.DictReader((tmp / "m.csv").open(encoding="utf-8")))
        by = {r["month"]: r for r in rows}
        self.assertEqual(by["2020-01"]["views"], "15")      # 개명 전 달은 옛 제목만
        self.assertEqual(by["2020-01"]["days"], "2")
        self.assertEqual(by["2021-01"]["views"], "101")     # 개명 뒤 넘겨주기 조회도 더한다
        self.assertEqual(by["2021-01"]["old_views"], "1")


class TestConsumerPartners(unittest.TestCase):
    def test_filter_partners_and_csv(self):
        tmp = Path(tempfile.mkdtemp())
        t = {"months": 12, "census_country": {"KR": "5800", "CN": "5700"},
             "items": [{"hs": "3304", "partners": ["KR"], "ids": ["kr-apr"]}]}
        resp = [["CTY_CODE", "GEN_VAL_MO", "I_COMMODITY", "time"], ["5800", "100", "3304", "2026-08"],
                ["5700", "999", "3304", "2026-08"], ["-", "5000", "3304", "2026-08"]]
        c = th.connect(tmp / "t.sqlite")
        with mock.patch.object(th.common, "load_yaml", lambda p: {"trade": t}), mock.patch.object(th.tp, "get", lambda *a, **k: json.dumps(resp)), \
                mock.patch.object(th, "CONSUMER_CSV", tmp / "p.csv"), mock.patch.object(th.time, "sleep", lambda s: None):
            n = th.consumer_partners(c, date(2026, 11, 14), {"CENSUS_API_KEY": "k"}, [])
        self.assertEqual(n, 1)                                   # 설정한 나라(KR)만 남는다
        self.assertEqual(c.execute("SELECT partner, value FROM obs").fetchall(), [("KR", 100.0)])
        self.assertEqual(th.surge(c, {"surge": {"window": 1, "min_value": {}, "min_yoy": 0, "top": 5}}), [])   # WORLD가 아니라 급등 산출에 섞이지 않는다
        rows = list(csv.reader((tmp / "p.csv").open(encoding="utf-8")))
        self.assertEqual(rows[1], ["2026-08", "3304", "KR", "100", "kr-apr"])
        c.close()

    def test_no_key_skips(self):
        c = th.connect(Path(tempfile.mkdtemp()) / "t.sqlite")
        with mock.patch.object(th.common, "load_yaml", lambda p: {"trade": {"items": []}}):
            self.assertEqual(th.consumer_partners(c, date(2026, 11, 14), {}, []), 0)
        c.close()


if __name__ == "__main__":
    unittest.main()
