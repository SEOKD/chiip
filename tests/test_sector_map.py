"""공통 섹터 지도·섹터 할당량·Pulse 섹터 확장 시험 (마스터 지시 2026-11-13 종목 범위 확대 1단계, ADR-025)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "sectors"))
sys.path.insert(0, str(ROOT / "radar"))
import sector_map as sm  # noqa: E402


def rows(*secs):
    return [{"id": f"r{i}", "score": 10 - i, "_s": s} for i, s in enumerate(secs)]


KEY = lambda r: r["_s"]  # noqa: E731


class Map(unittest.TestCase):
    def test_name_rules_order(self):
        self.assertEqual(sm.by_name("TradingView 1_US SEMICONDUCTORS · DRAM HBM"), "memory_storage")
        self.assertEqual(sm.by_name("TradingView 1_US SEMI EQUIPMENT & PARTS OSAT"), "semicap")
        self.assertEqual(sm.by_name("TradingView 1_US AEROSPACE & DEFENSE"), "defense")
        self.assertEqual(sm.by_name("TradingView 1_US AEROSPACE"), "space")
        self.assertEqual(sm.by_name("TradingView 1_US HEALTHCARE"), "health")
        self.assertEqual(sm.by_name("TradingView 2_Korea 조선"), "shipbuild")
        self.assertIsNone(sm.by_name("TradingView 1_US CHIIP PICKS"))

    def test_real_tags(self):
        self.assertEqual(sm.tag("co-ttm"), "elec_components")      # 내 종목 holding_group
        self.assertEqual(sm.tag(ticker="LLY"), "health")            # Portfolio 섹터 묶음 구성 종목
        self.assertEqual(sm.tag("de-rheinmetall"), "defense")
        self.assertTrue(sm.is_ai("power_infra"))
        self.assertFalse(sm.is_ai("health"))

    def test_unknown_is_none(self):
        self.assertIsNone(sm.tag("zz-nope", "ZZZZQ"))


class Quota(unittest.TestCase):
    def test_non_ai_min_and_per_sector(self):
        r = rows("ai_compute", "ai_compute", "ai_compute", "semicap", "power_infra", "health", "defense", "health")
        got = [x["_s"] for x in sm.diversify(r, 5, key=KEY, non_ai_min=0.4, per_sector_max=2)]
        self.assertEqual(len(got), 5)
        self.assertGreaterEqual(sum(1 for s in got if not sm.is_ai(s)), 2)
        self.assertLessEqual(got.count("ai_compute"), 2)

    def test_keeps_score_order(self):
        r = rows("ai_compute", "health", "semicap", "defense")
        got = [x["id"] for x in sm.diversify(r, 3, key=KEY, non_ai_min=0.4, per_sector_max=2)]
        self.assertEqual(got, sorted(got))

    def test_relaxes_when_short(self):
        r = rows("ai_compute", "ai_compute", "ai_compute")
        self.assertEqual(len(sm.diversify(r, 3, key=KEY, non_ai_min=0.4, per_sector_max=2)), 3)

    def test_unknown_sector_not_counted_as_non_ai(self):
        r = rows(None, None, "ai_compute", "health")
        got = [x["_s"] for x in sm.diversify(r, 2, key=KEY, non_ai_min=0.5, per_sector_max=2)]
        self.assertIn("health", got)


class Pulse(unittest.TestCase):
    def setUp(self):
        import pulse
        self.p = pulse

    def test_sector_hit(self):
        self.assertEqual(self.p.sector_hit({"title": "Eli Lilly (NYSE: LLY) announces FDA approval"}), "health")
        self.assertEqual(self.p.sector_hit({"title": "Lockheed Martin (NYSE: LMT) awarded contract"}), "defense")
        self.assertIsNone(self.p.sector_hit({"title": "NVIDIA (NASDAQ: NVDA) reports record results"}))   # AI는 기존 경로
        self.assertIsNone(self.p.sector_hit({"title": "Eli Lilly (NYSE: LLY) to present at conference"}))   # 사건 어휘 없음

    def test_sector_cap(self):
        src = [{"source_class": "섹터 확장", "sector": s, "title": str(i)} for i, s in enumerate(["health", "health", "health", "defense", "energy", "energy"])]
        got = self.p._sector_cap(src, 4)
        self.assertEqual(len(got), 4)
        self.assertEqual([g["sector"] for g in got].count("health"), 2)


if __name__ == "__main__":
    unittest.main()
