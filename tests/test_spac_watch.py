"""SPAC 감지·생애 단계 장부 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import spac_watch as sw  # noqa: E402


def f(form, date, items=()):
    return {"cik": "1", "name": "Test Acquisition Corp", "tickers": "TSTA", "form": form, "date": date, "items": list(items), "url": "u"}


class T(unittest.TestCase):
    def test_parse_display_name(self):
        p = sw.parse({"display_names": ["Lake Superior Acquisition Corp  (LKSP, LKSPR, LKSPU)  (CIK 0002043508)"], "adsh": "0001-26-1", "form": "8-K", "file_date": "2026-11-04", "items": ["1.01"]})
        self.assertEqual((p["cik"], p["tickers"]), ("2043508", "LKSP,LKSPR,LKSPU"))

    def test_stage_moves_forward_only(self):
        reg = {}
        self.assertEqual(sw.apply(reg, f("424B4", "2026-01-01"), "S0", "t")[5], "S0")
        self.assertEqual(sw.apply(reg, f("425", "2026-03-01"), "S2", "t")[4:6], ["S0", "S2"])
        self.assertIsNone(sw.apply(reg, f("424B4", "2026-04-01"), "S0", "t"))
        self.assertEqual(reg["1"]["stage"], "S2")

    def test_effect_before_deal_is_ignored(self):
        reg = {}
        sw.apply(reg, f("424B4", "2026-01-01"), "S0", "t")
        self.assertIsNone(sw.stage_of("S3|S2", f("EFFECT", "2026-01-02"), reg))   # IPO 등록 효력
        sw.apply(reg, f("425", "2026-03-01"), "S2", "t")
        self.assertEqual(sw.stage_of("S3|S2", f("EFFECT", "2026-06-01"), reg), "S3")

    def test_vote_8k_needs_507_and_deal(self):
        reg = {}
        sw.apply(reg, f("425", "2026-03-01"), "S2", "t")
        self.assertIsNone(sw.stage_of("S4|S2", f("8-K", "2026-06-01", ["8.01"]), reg))
        self.assertEqual(sw.stage_of("S4|S2", f("8-K", "2026-06-01", ["5.07"]), reg), "S4")

    def test_close_needs_201(self):
        self.assertEqual(sw.stage_of("CLOSE?", f("8-K", "d", ["2.01", "9.01"])), "S5")
        self.assertIsNone(sw.stage_of("CLOSE?", f("8-K", "d", ["8.01"])))

    def test_extension_counts_not_stage(self):
        reg = {}
        sw.apply(reg, f("424B4", "2026-01-01"), "S0", "t")
        self.assertIsNone(sw.apply(reg, f("DEF 14A", "2026-09-01"), "EXT", "t"))
        self.assertEqual((reg["1"]["stage"], reg["1"]["extensions"]), ("S0", "1"))


if __name__ == "__main__":
    unittest.main()
