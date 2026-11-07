"""대만 공시 재무 파이프라인 (마스터 지시 2026-11-07)"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "radar" / "reverse" / "collectors"))
from pollers import tw_financials as tf  # noqa: E402

NOTICE = """1.提報董事會或經董事會決議日期:115/11/05
3.財務報告或年度自結財務資訊報導期間
起訖日期(XXX/XX/XX~XXX/XX/XX):115/01/01~115/09/30
4.1月1日累計至本期止營業收入(仟元):42,478,500
5.1月1日累計至本期止營業毛利(毛損) (仟元):13,558,722
6.1月1日累計至本期止營業利益(損失) (仟元):8,457,727
7.1月1日累計至本期止稅前淨利(淨損) (仟元):9,511,617
8.1月1日累計至本期止本期淨利(淨損) (仟元):8,059,305
9.1月1日累計至本期止歸屬於母公司業主淨利(損) (仟元):8,319,555
10.1月1日累計至本期止基本每股盈餘(損失) (元):4.52
11.期末總資產(仟元):222,677,178
12.期末總負債(仟元):123,523,741
13.期末歸屬於母公司業主之權益(仟元):66,550,401"""


def statement(code, year, season, rev, op, eps, tpex=False):
    k = ("SecuritiesCompanyCode", "CompanyName", "Year", "Season") if tpex else ("公司代號", "公司名稱", "年度", "季別")
    return {k[0]: code, k[1]: "台光電", k[2]: year, k[3]: season, "營業收入": f"{rev}.00", "營業成本": "", "營業利益（損失）": str(op), "基本每股盈餘（元）": str(eps)}


class TestParse(unittest.TestCase):
    def test_board_notice_ytd_numbers(self):
        q, v = tf.parse_notice(NOTICE)
        self.assertEqual(q, "2026Q3")
        self.assertEqual((v["rev"], v["gp"], v["op"], v["ni"], v["ni_parent"], v["eps"]), (42478500, 13558722, 8457727, 8059305, 8319555, 4.52))
        self.assertEqual((v["assets"], v["liab"], v["equity_parent"]), (222677178, 123523741, 66550401))

    def test_notice_not_from_january_is_ignored(self):
        self.assertEqual(tf.parse_notice("起訖日期:115/07/01~115/09/30\n4.營業收入(仟元):1"), (None, {}))

    def test_rows_both_markets_and_blank_cells(self):
        rows = [statement("2383", "115", "3", 100, 40, 8.5), statement("6274", "115", "3", 50, 5, 1.1, tpex=True), statement("9999", "115", "3", 1, 1, 1)]
        got = tf.parse_rows(rows, tf.IS_FIELDS, {"2383": {}, "6274": {}})
        self.assertEqual(set(got), {"2383", "6274"})
        q, _, v = got["6274"]
        self.assertEqual((q, v["rev"], v["cogs"]), ("2026Q3", 50.0, None))   # 빈칸은 None(0으로 채우지 않는다)


class TestQuarters(unittest.TestCase):
    def doc(self, *ytd):
        d = {"code": "2383", "market": "twse", "ytd": {}}
        for q, rev, op, eps in ytd:
            tf.merge(d, q, "is", {"rev": rev, "op": op, "eps": eps}, "statement", "u", "t")
        return d

    def test_ytd_differences(self):
        q = {r["quarter"]: r for r in tf.quarters(self.doc(("2026Q1", 100, 30, 2.0), ("2026Q2", 250, 70, 4.5), ("2026Q3", 400, 120, 7.25)))}
        self.assertEqual((q["2026Q1"]["rev"], q["2026Q2"]["rev"], q["2026Q3"]["rev"]), (100, 150, 150))
        self.assertEqual((q["2026Q2"]["op"], q["2026Q3"]["eps"]), (40, 2.75))
        self.assertEqual(q["2026Q3"]["period"], "2026-09-30")

    def test_missing_previous_ytd_leaves_quarter_empty(self):
        q = tf.quarters(self.doc(("2026Q1", 100, 30, 2.0), ("2026Q3", 400, 120, 7.0)))[-1]
        self.assertIsNone(q["rev"])   # 2분기 누계가 없으면 3분기를 추측하지 않는다

    def test_q4_uses_annual_minus_nine_months(self):
        q = tf.quarters(self.doc(("2025Q3", 300, 90, 6.0), ("2025Q4", 420, 130, 8.0)))[-1]
        self.assertEqual((q["quarter"], q["rev"], q["op"]), ("2025Q4", 120, 40))

    def test_statement_beats_notice_but_not_reverse(self):
        d = self.doc(("2026Q3", 400, 120, 7.0))
        self.assertFalse(tf.merge(d, "2026Q3", "is", {"rev": 1}, "board_notice", "u", "t"))
        self.assertEqual(d["ytd"]["2026Q3"]["is"]["rev"], 400)
        d2 = {"ytd": {}}
        tf.merge(d2, "2026Q3", "is", {"rev": 1}, "board_notice", "u", "t")
        self.assertTrue(tf.merge(d2, "2026Q3", "is", {"rev": 2}, "statement", "u", "t"))

    def test_quarters_hist_shape_in_won_units(self):
        h = tf.quarters_hist(self.doc(("2026Q1", 100, 30, 2.0), ("2026Q2", 250, 70, 4.5)))
        self.assertEqual((h["currency"], h["key"]), ("TWD", "TW_2383"))
        self.assertEqual(h["q"][1], {"period": "2026-06-30", "rev": 150000, "cogs": None, "gp": None, "sga": None, "rd": None, "da": None, "other": None, "op": 40000, "opex": None})


class TestRun(unittest.TestCase):
    def test_run_saves_and_status_reads(self):
        tables = {tf.TABLES["twse"]["is"]: [statement("2383", "115", "3", 141226994, 38548717, 82.9)], tf.TABLES["twse"]["bs"]: [],
                  tf.TABLES["tpex"]["is"]: [], tf.TABLES["tpex"]["bs"]: []}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(tf, "OUT", Path(d)), mock.patch.object(tf, "MONTHLY", Path(d) / "none.csv"), \
                mock.patch.object(tf, "universe", lambda: {"2383": {"id": "co-elitematerial", "name": "엘리트머티리얼즈"}}), \
                mock.patch.object(tf.common, "record_health", lambda *a: None):
            self.assertEqual(tf.run(fetch=tables.__getitem__)[:2], (1, 1))
            self.assertEqual(tf.run(fetch=tables.__getitem__)[0], 0)   # 같은 값이면 다시 쓰지 않는다
            doc = tf.load("2383")
            self.assertEqual((doc["name"], doc["ytd"]["2026Q3"]["basis"]["is"]), ("엘리트머티리얼즈", "statement"))
            self.assertIn("누계 매출 1,412.3억 대만달러 · 영업이익 385.5억 대만달러", tf.status()[0])

    def test_all_tables_failing_raises(self):
        def boom(url):
            raise OSError("down")
        with mock.patch.object(tf, "universe", lambda: {}), mock.patch.object(tf.common, "record_health", lambda *a: None):
            with self.assertRaises(RuntimeError):
                tf.run(fetch=boom)


class TestUniverse(unittest.TestCase):
    def test_named_targets_are_in_universe_with_korean_names(self):
        u = tf.universe()
        for code in ("2330", "3711", "2454", "3037", "2383", "2408", "2360", "3035"):   # TSMC·ASE·미디어텍·유니마이크론·엘리트머티리얼즈·난야·크로마·패러데이
            self.assertIn(code, u)
        self.assertEqual(u["3037"]["name"], "유니마이크론")
        self.assertEqual(tf.ko_name("日月光投控"), "ASE")


class TestMonthlyTpex(unittest.TestCase):
    def test_tpex_json_matches_twse_csv_columns(self):
        import twse_monthly as tm
        row = {k: str(i) for i, k in enumerate(tm.TPEX_KEYS)}
        with mock.patch.object(tm.common, "http_get", return_value=__import__("json").dumps([row]).encode()):
            r = tm.tpex_rows()[0]
        self.assertEqual((r[1], r[2], r[5], r[10], r[12]), ("1", "2", "5", "10", "12"))   # run()이 읽는 열 위치


if __name__ == "__main__":
    unittest.main()
