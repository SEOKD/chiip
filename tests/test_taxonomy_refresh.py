"""시장 세부 산업 분류 자동 갱신·나라 구분 없음·TradingView 섹션 (마스터 지시 2026-11-08)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "industry"))
sys.path.insert(0, str(ROOT / "radar"))
import taxonomy_refresh as TR  # noqa: E402
import tv_sections as TS  # noqa: E402
import weekly_pick as W  # noqa: E402


class TestTaxonomy(unittest.TestCase):
    def test_groups_are_recounted_not_fixed(self):
        c = W.cfg()
        self.assertEqual(len(c["industries"]), len(c["_members"]))
        self.assertGreater(len(W.classify()), 280)

    def test_country(self):
        self.assertEqual(TR.country({"ticker": "005930"}), "KR")
        self.assertEqual(TR.country({"ticker": "2330"}), "?")            # 4자리 숫자는 일본·대만이 겹쳐 추측하지 않는다
        self.assertEqual(TR.country({"ticker": "2330", "region": "TW"}), "TW")
        self.assertEqual(TR.country({"ticker": "ABBN.SW"}), "CH")

    def test_groups_mix_countries(self):
        cs = TR.countries()
        self.assertTrue(any(len(v) >= 3 for v in cs.values()))   # 같은 세부 산업이면 나라를 섞어 한 묶음

    def test_tv_map_learned_by_majority(self):
        tm = TR.load().get("tv_map") or {}
        self.assertEqual(tm.get("Semiconductors"), "Semiconductors")
        self.assertEqual(tm.get("Engineering & Construction"), "Construction & Engineering")

    def test_tv_plan_keeps_every_symbol(self):
        wl = {"name": "1_US", "id": 1, "symbols": ["###SEMICONDUCTOR", "NASDAQ:NVDA", "NASDAQ:ZZZZ", "###HVAC", "NYSE:JCI"]}
        out, moved, add = TS.taxonomy_plan(wl, {"NASDAQ:NVDA": ("1_US", "SEMICONDUCTORS · AI ACCELERATORS"), "NYSE:PWR": ("1_US", "CONSTRUCTION & ENGINEERING")}, set(wl["symbols"]))
        self.assertIn("NASDAQ:ZZZZ", out)        # 유니버스 밖 종목은 그대로 남는다
        self.assertIn("NYSE:PWR", add)           # 어느 와치리스트에도 없는 유니버스 종목은 더한다
        self.assertLess(out.index("###SEMICONDUCTORS · AI ACCELERATORS"), out.index("NASDAQ:NVDA"))


if __name__ == "__main__":
    unittest.main()
