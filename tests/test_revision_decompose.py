"""그림 8 분기별 주가 분해 — 분해 불가 구간을 빼지 않는다(2026-11-15 LBRT: 4개 분기 중 1개만, 그것도 리비전 −90% × 멀티플 +431%)"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import revision_view as rv  # noqa: E402


class TestDecompose(unittest.TestCase):
    def test_liberty_keeps_four_quarters(self):
        f = ROOT / "knowledge/models/companies/co-liberty/datapack.json"
        if not f.exists():
            self.skipTest("co-liberty 없음")
        dp = json.loads(f.read_text(encoding="utf-8"))
        h, px = rv.load_hist(dp["consensus"]["eps_history"]["rows"]), rv.load_prices(dp["id"])
        if not px:
            self.skipTest("시세 없음")
        dec = rv.decompose(h, dp["revision_events"], px)
        self.assertEqual(len(dec), 4)
        for x in dec:   # 적자·0 근처면 멀티플을 만들지 않는다
            if x["rev"] is None:
                self.assertIsNone(x["rerate"])
                self.assertTrue(x["why"])
            else:
                self.assertLess(abs(x["rerate"]), 3)


if __name__ == "__main__":
    unittest.main()
