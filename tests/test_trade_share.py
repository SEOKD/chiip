"""미국 수입 나라별 비중(HTS 10단위) 시험 (2026-11-21)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import trade_share as ts  # noqa: E402
import usitc_dataweb as dw  # noqa: E402

H = ["CTY_CODE", "GEN_VAL_MO", "GEN_QY1_MO", "UNIT_QY1", "I_COMMODITY", "COMM_LVL", "time"]
CODES = {"KR": "5800", "JP": "5880"}
IT = {"hts": "1902300060", "name": "라면", "focus": "KR", "partners": ["KR", "JP"], "ids": ["kr-samyang"]}


def resp(month, kr, world, kg=1000):
    return [[c, str(v), str(kg), "KG", "1902300060", "HS10", month] for c, v in (("5800", kr), ("-", world), ("1220", 5))]


class T(unittest.TestCase):
    def test_share_and_unit_price(self):
        r = ts.parse([H] + resp("2026-09", 70, 100, 20), "1902300060", CODES, {"KR", "JP"})
        kr = r[("2026-09", "1902300060", "KR")]
        self.assertEqual(kr["share"], 0.7)
        self.assertEqual(kr["usd_per_kg"], 3.5)
        self.assertEqual(r[("2026-09", "1902300060", "WORLD")]["share"], 1.0)
        self.assertNotIn(("2026-09", "1902300060", "CA"), r)   # 설정 밖 나라는 버린다

    def test_changes_only_new_months(self):
        rows = {}
        for m, kr in (("2025-09", 50), ("2026-08", 80), ("2026-09", 70)):
            rows.update(ts.parse([H] + resp(m, kr, 100), "1902300060", CODES, {"KR"}))
        ch = ts.changes(rows, IT, {"2026-09"}, {"alert_pp": 5, "alert_yoy": 0.3})
        self.assertEqual({x["type"] for x in ch}, {"share_move", "value_yoy"})
        self.assertEqual(ts.changes(rows, IT, set(), {"alert_pp": 5, "alert_yoy": 0.3}), [])

    def test_no_key_no_call(self):
        self.assertIn("skipped", ts.run(env={}))

    def test_dataweb_table_parse(self):
        resp_ = {"dto": {"tables": [{"column_groups": [{"columns": [{"label": "HTS Number"}, {"label": "2024"}]}],
                                     "row_groups": [{"rowsNew": [{"rowEntries": [{"value": "1902300060"}, {"value": "1,000"}]}]}]}]}}
        t = dw.tables(resp_)
        self.assertEqual(t[0]["columns"], ["HTS Number", "2024"])
        self.assertEqual(t[0]["rows"], [["1902300060", "1,000"]])


if __name__ == "__main__":
    unittest.main()
