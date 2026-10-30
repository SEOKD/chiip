"""원자력·위성 밸류체인 발굴 시험 — 지도·레이더 연결·구간 섹터(2026-10-31)"""
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))

from pollers import common, gate  # noqa: E402
import bands  # noqa: E402

THEMES = ("nuclear_fuel", "nuclear_reactor", "satellite_launch", "satellite_data")


def themes():
    return (yaml.safe_load((ROOT / "config" / "discovery.yaml").read_text(encoding="utf-8")) or {})["themes"]


class TestMap(unittest.TestCase):
    def test_named_stocks_are_on_the_map(self):
        by_theme = {t["id"]: {c["code"] for c in t["candidates"]} for t in themes() if t["id"] in THEMES}
        self.assertEqual(set(by_theme), set(THEMES))
        self.assertLessEqual({"CCJ", "LEU"}, by_theme["nuclear_fuel"])
        self.assertIn("BAB", by_theme["nuclear_reactor"])
        self.assertLessEqual({"YSS", "RKLB"}, by_theme["satellite_launch"])
        self.assertIn("PL", by_theme["satellite_data"])

    def test_no_candidate_twice(self):
        ids = [c["id"] for t in themes() for c in t["candidates"]]
        self.assertEqual(sorted(i for i in set(ids) if ids.count(i) > 1), [])

    def test_every_candidate_explains_itself(self):
        for t in themes():
            if t["id"] in THEMES:
                self.assertTrue(t.get("watch"))
                self.assertTrue(t.get("bottleneck") and t.get("driver") and t.get("evidence"))
                for c in t["candidates"]:
                    self.assertTrue(c.get("why") and c.get("edge") is not None and c.get("market"), c["id"])


class TestRadarWiring(unittest.TestCase):
    def test_recognition_filings_and_gate(self):
        ids = common.watch_theme_ids()
        self.assertLessEqual({"us-ccj", "us-leu", "gb-babcock", "us-yss", "us-rklb", "us-pl"}, ids)
        self.assertNotIn("tw-yageo", ids)                                # 다른 테마는 그대로
        sec = {e["id"]: e for e in common.edge_watch_entries()}
        self.assertEqual(sec["us-yss"]["code"], "YSS.US")
        self.assertIn("York Space Systems", sec["us-yss"]["aliases"])
        self.assertNotIn("gb-babcock", sec)                              # SEC는 미국 상장만
        gate._CACHE.pop("extra_focus", None)
        self.assertLessEqual({"us-ccj", "us-yss"}, gate.extra_focus())
        names = {cid: n for cid, n, _ in common.discovery_entities()}
        self.assertIn("Centrus Energy", names["us-leu"])

    def test_keys_and_company_lines(self):
        keys = (yaml.safe_load((ROOT / "config" / "fiscal_keys.yaml").read_text(encoding="utf-8")) or {})["keys"]
        lines = (yaml.safe_load((ROOT / "config" / "company_lines.yaml").read_text(encoding="utf-8")) or {})["lines"]
        for t in themes():
            if t["id"] in THEMES:
                for c in t["candidates"]:
                    if c["market"] == "us":
                        self.assertIn(c["id"], keys)
                    self.assertTrue(lines.get(c["id"]) or c["id"] in ("gb-babcock", "co-doosanenerbility"), c["id"])


class TestBands(unittest.TestCase):
    def test_sector_has_exit_multiple(self):
        secs = bands.cfg()["sectors"]
        for theme, name in (("nuclear_fuel", "nuclear"), ("nuclear_reactor", "nuclear"), ("satellite_launch", "space"), ("satellite_data", "space")):
            self.assertEqual(bands.THEME_SECTOR[theme], name)
            self.assertGreater(secs[name]["exit_ev_sales"], 0)


if __name__ == "__main__":
    unittest.main()
