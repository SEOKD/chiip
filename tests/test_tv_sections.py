"""TradingView 와치리스트 섹션 재분배 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import tv_sections as ts  # noqa: E402


class T(unittest.TestCase):
    def test_moves_merge_and_keep_all(self):
        syms = ["###ALL", "A:X", "A:Y", "###SEMI", "A:S1", "###SEMIS", "A:S2", "###UTIL", "A:NE"]
        rule = {"merge": {"SEMIS": "SEMI"}, "new_sections": ["ENERGY"], "moves": {"A:X": "SEMI", "A:NE": "ENERGY"}}
        out, moved, loose = ts.plan(syms, rule)
        self.assertEqual(out, ["###ALL", "A:Y", "###SEMI", "A:X", "A:S1", "A:S2", "###ENERGY", "A:NE"])
        self.assertEqual(moved, 3)   # X·S2(합침)·NE
        self.assertEqual(sorted(x for x in out if not x.startswith("###")), sorted(x for x in syms if not x.startswith("###")))

    def test_unsectioned_stay_front(self):
        out, _, loose = ts.plan(["A:Q", "###B", "A:R"], {})
        self.assertEqual(out, ["A:Q", "###B", "A:R"])
        self.assertEqual(loose, ["A:Q"])


if __name__ == "__main__":
    unittest.main()
