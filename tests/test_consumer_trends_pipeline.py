"""한국 외 소비 트렌드 파이프라인(radar/consumer_macro.py · consumer_discovery.py, 2026-11-14 마스터 지시) 오프라인 시험"""
import io
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import consumer_discovery as cd  # noqa: E402
import consumer_macro as cm  # noqa: E402

ALERT = {"accel_pp": 3.0, "z": 1.5, "accel_pp_noisy": 8.0}


def months(start, n):
    return [cm.shift(start, k) for k in range(n)]


class TestMetrics(unittest.TestCase):
    def test_shift(self):
        self.assertEqual(cm.shift("2026-01", -1), "2025-12")
        self.assertEqual(cm.shift("2025-11", 3), "2026-02")

    def test_level_yoy3_accel_z(self):
        s = {m: 100.0 for m in months("2019-01", 84)}          # 평평(2019-01~2025-12) — 마지막 3개월만 10% 높게
        for m in months("2025-10", 3):
            s[m] = 110.0
        last = max(s)                                          # 2025-12
        r = cm.metrics(s)
        self.assertEqual(r["month"], last)
        self.assertAlmostEqual(r["yoy3"], 0.10, 6)
        self.assertAlmostEqual(r["accel_pp"], 10.0, 4)          # 3개월 전 3개월 YoY = 0
        self.assertIsNone(r["z"])                               # 과거 YoY 분산 0 → z 없음

    def test_fallback_when_last_year_missing(self):
        s = {m: 100.0 + i for i, m in enumerate(months("2018-01", 106))}   # 2026-10까지
        del s["2025-10"]                                        # 셧다운으로 비었다
        r = cm.metrics(s)
        self.assertEqual(r["latest"], "2026-10")
        self.assertEqual(r["month"], "2026-09")                 # 전년 비교가 되는 가장 최근 달

    def test_yoy_kind(self):
        s = {m: 2.0 for m in months("2020-01", 70)}
        r = cm.metrics(s, kind="yoy")
        self.assertAlmostEqual(r["yoy3"], 0.02, 6)
        self.assertAlmostEqual(r["accel_pp"], 0.0, 6)

    def test_flag_needs_same_direction(self):
        self.assertEqual(cm.flag({"accel_pp": 4, "z": 2}, False, ALERT), "up")
        self.assertEqual(cm.flag({"accel_pp": -4, "z": -2}, False, ALERT), "down")
        self.assertIsNone(cm.flag({"accel_pp": -13.5, "z": 1.7}, True, ALERT))   # 높은데 둔화 — 경보 아님(일본 게임 소프트)
        self.assertIsNone(cm.flag({"accel_pp": 5, "z": 2}, True, ALERT))         # 잡음 품목은 ±8%p
        self.assertIsNone(cm.flag({"accel_pp": None, "z": 2}, False, ALERT))


class TestParsers(unittest.TestCase):
    def test_jsonstat(self):
        d = {"id": ["geo", "time"], "size": [2, 2],
             "dimension": {"geo": {"category": {"index": {"DE": 0, "FR": 1}}}, "time": {"category": {"index": {"2026-08": 0, "2026-09": 1}}}},
             "value": {"0": 1.0, "1": 2.0, "3": 4.0}}
        got = sorted((c["geo"], c["time"], v) for c, v in cm.jsonstat_rows(d))
        self.assertEqual(got, [("DE", "2026-08", 1.0), ("DE", "2026-09", 2.0), ("FR", "2026-09", 4.0)])

    def test_month_labels(self):
        self.assertEqual(cm.ons_month("2026 SEP"), "2026-09")
        self.assertIsNone(cm.ons_month("2026 Q3"))
        self.assertEqual(cm.estat_month("2026000909"), "2026-09")
        self.assertEqual(cm.eu_id("EU27_2020", "total"), "eu-eu27-total")

    def test_xlsx_and_jnto(self):
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        rid = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
        shared = (f'<sst {ns}><si><t>総数</t><rPh sb="0" eb="2"><t>ソウスウ</t></rPh></si><si><t>中国</t></si><si><t>1月</t></si><si><t>2月</t></si></sst>')
        sheet = (f'<worksheet {ns}><sheetData><row r="1"><c r="C1" t="s"><v>2</v></c><c r="E1" t="s"><v>3</v></c></row>'
                 '<row r="2"><c r="A2" t="s"><v>0</v></c><c r="C2"><v>3500000</v></c><c r="E2"><v>3400000</v></c></row>'
                 '<row r="3"><c r="A3" t="s"><v>1</v></c><c r="C3"><v>385519</v></c></row></sheetData></worksheet>')
        wb = f'<workbook {ns} {rid}><sheets><sheet name="2026" sheetId="1" r:id="rId1"/><sheet name="注記" sheetId="2" r:id="rId2"/></sheets></workbook>'
        rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Target="worksheets/sheet2.xml"/></Relationships>')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("xl/sharedStrings.xml", shared)
            z.writestr("xl/workbook.xml", wb)
            z.writestr("xl/_rels/workbook.xml.rels", rels)
            z.writestr("xl/worksheets/sheet1.xml", sheet)
            z.writestr("xl/worksheets/sheet2.xml", f'<worksheet {ns}><sheetData/></worksheet>')
        sheets = cm.xlsx_sheets(buf.getvalue())
        self.assertEqual(sheets["2026"][1][0], "総数")             # 후리가나(rPh)는 빠진다
        got = cm.jnto_series(sheets, [{"id": "t", "label": "総数"}, {"id": "cn", "label": "中国"}])
        self.assertEqual(got["t"], {"2026-01": 3500000.0, "2026-02": 3400000.0})
        self.assertEqual(got["cn"], {"2026-01": 385519.0})


class TestRelease(unittest.TestCase):
    def test_first_run_sets_baseline_then_alerts(self):
        row = {"id": "us-x", "family": "us", "name": "의류", "month": "2026-09", "flag": "up", "yoy3": 0.08, "accel_pp": 4.0, "z": 2.0, "exposure": ["TJX"]}
        st = {}
        self.assertEqual(cm.releases({"us-x": row}, st, date(2026, 11, 14)), [])      # 처음 켠 날 — 기준만
        self.assertEqual(st["months"]["us"], "2026-09")
        self.assertEqual(cm.releases({"us-x": row}, st, date(2026, 11, 14)), [])      # 같은 달 — 다시 보내지 않는다
        items = cm.releases({"us-x": dict(row, month="2026-10")}, st, date(2026, 11, 20))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source_id"], "src-consumer-macro")
        self.assertIn("TJX", items[0]["snippet"])
        quiet = cm.releases({"us-x": dict(row, month="2026-11", flag=None)}, st, date(2026, 12, 20))
        self.assertEqual(quiet, [])                                                   # 문턱 없으면 보내지 않는다(조용한 달)


class TestDiscovery(unittest.TestCase):
    LEX = [(cd.norm("Hoka"), "DECK", "데커스", False), (cd.norm("Pokémon"), "7974.T", "닌텐도", True), (cd.norm("Elden Ring Nightreign"), "7832.T", "반다이남코", True),
           (cd.norm("Elden Ring"), "9468.T", "가도카와", True), (cd.norm("ラブブ"), "9992.HK", "팝마트", False)]

    def test_title_and_query(self):
        tb = lambda t: (cd.title_brand(t, self.LEX) or {}).get("company")
        self.assertEqual(tb("Hoka"), "데커스")
        self.assertEqual(tb("Pokémon_Legends:_Z-A"), "닌텐도")
        self.assertEqual(tb("Elden Ring Nightreign"), "반다이남코")      # 긴 이름이 먼저
        self.assertEqual(tb("ラブブ"), "팝마트")
        self.assertIsNone(tb("Hokage"))
        qb = lambda q: (cd.query_brand(q, self.LEX) or {}).get("company")
        self.assertEqual(qb("pokemon go"), "닌텐도")                      # 악센트 접기
        self.assertEqual(qb("hoka shoes sale"), "데커스")
        self.assertIsNone(qb("hokanson"))                                # 단어 경계

    def test_traffic(self):
        self.assertEqual(cd.traffic("200K+"), 200000)
        self.assertEqual(cd.traffic("2,000+"), 2000)
        self.assertEqual(cd.traffic("1M+"), 1000000)

    def test_apple_rising_needs_baseline(self):
        con = cd.connect(Path(tempfile.mkdtemp()) / "d.sqlite")
        a = {"countries": ["us"], "feeds": ["top-free"], "top": 25, "jump": 50}
        iss = [{"ticker": "NTDOY", "name": "닌텐도", "rx": "^Nintendo"}]
        con.execute("insert into apple values('2026-11-14','us','top-free',3,'1','Mario App','Nintendo Co., Ltd.')")
        self.assertEqual(cd.apple_rising(con, "2026-11-14", a, iss), ([], None))      # 기준선 없음
        con.execute("insert into apple values('2026-11-07','us','top-free',80,'2','Other','X Inc')")
        con.execute("insert into apple values('2026-11-07','us','top-free',90,'3','Climber','Y Inc')")
        con.execute("insert into apple values('2026-11-14','us','top-free',5,'3','Climber','Y Inc')")
        rows, base = cd.apple_rising(con, "2026-11-14", a, iss)
        self.assertEqual(base, "2026-11-07")
        kinds = {r["name"]: r["kind"] for r in rows}
        self.assertEqual(kinds, {"Mario App": "신규 진입", "Climber": "급상승"})
        al = cd.alerts({"apple": rows})
        self.assertEqual(len(al), 1)                                     # 상장사에 매핑된 것만
        self.assertIn("닌텐도", al[0]["headline"])

    def test_wiki_rising_and_dedupe(self):
        con = cd.connect(Path(tempfile.mkdtemp()) / "w.sqlite")
        end = date(2026, 11, 11)
        for k in range(35):
            d = (end - timedelta(days=k)).isoformat()
            con.execute("insert into wiki values(?,?,?,?,?)", (d, "en.wikipedia", "Steady", 5, 20000))
            if k < 7:
                con.execute("insert into wiki values(?,?,?,?,?)", (d, "en.wikipedia", "Hoka", 9, 30000))
                con.execute("insert into wiki values(?,?,?,?,?)", (d, "en.wikipedia", "Hoka (company)", 9, 20000))
        w = {"projects": ["en.wikipedia"], "min_views7": {"en": 100000}, "accel": 3.0, "top": 15}
        rows = cd.wiki_rising(con, w, self.LEX)
        self.assertEqual({r["title"] for r in rows}, {"Hoka", "Hoka (company)"})   # 평평한 문서는 빠진다
        al = cd.alerts({"wiki": rows})
        self.assertEqual(len(al), 1)                                     # 같은 회사·같은 용어는 한 건


if __name__ == "__main__":
    unittest.main()
