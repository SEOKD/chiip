"""내러티브 프리미엄 근거 수집(radar/narrative_sources.py)·알파 메시지 내러티브 줄 오프라인 시험 — 마스터 지시 2026-10-28"""
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))

import narrative_sources as ns  # noqa: E402
import alpha_watch  # noqa: E402
from pollers import common  # noqa: E402

VICOR = {"id": "co-vicor", "name": "Vicor", "names": ["Vicor"], "ticker": "VICR", "sub": "power_infra"}


class TestNarrativeSources(unittest.TestCase):
    def test_mention_is_word_bounded(self):
        pat = ns.mention_re(VICOR)
        self.assertTrue(pat.search("Vicor: Buy The Dip In This Key AI Power Enabler (NASDAQ:VICR)"))
        self.assertTrue(pat.search("Biggest movers: VICR, PPG"))
        self.assertIsNone(pat.search("Why were Victorian elites so effective?"))   # HN 접두 매칭 잡음
        self.assertIsNone(pat.search("Victory! Court Rules OPM Data Disclosure Is Unlawful"))

    def test_keep_titles_drops_unrelated_and_reposts(self):
        items = [{"title": "Vicor Stock Surges as Royalty Revenue Boosts Growth Outlook - Barron's"},
                 {"title": "Vicor Stock Surges as Royalty Revenue Boosts Growth Outlook - MarketBeat"},   # 같은 제목 재게재
                 {"title": "Crude oil drops as Saudi defense minister travels to Tehran - Seeking Alpha"}]
        kept, dropped = ns.keep_titles(items, ns.mention_re(VICOR))
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, 2)

    def test_company_lookup_has_ticker_and_sector_query(self):
        co = ns.company("co-vicor")
        self.assertEqual(co["ticker"], "VICR")
        self.assertIn(co["sub"], ns.SECTOR_TERMS)
        self.assertIsNone(ns.company("co-없는종목"))

    def test_excluded_sources_not_collected(self):
        c = ns.cfg()
        sites = " ".join(c["auto"]["community_headlines"]["sites"])
        feeds = " ".join(s["feed"] for s in c["auto"]["substack"])
        for blocked in ("reddit.com", "valueinvestorsclub.com", "stocktwits.com", "x.com", "twitter.com"):
            self.assertNotIn(blocked, sites + feeds)
        self.assertIn("reddit", c["excluded"])

    def test_registry_parses_with_new_sector_narratives(self):
        reg = common.load_yaml("knowledge/narratives/registry.yaml")
        ids = {n["id"] for n in reg["narratives"]}
        self.assertTrue({"nar-wfe-cycle-2028", "nar-dc-high-voltage-power", "nar-ai-pcb-content"} <= ids)


class TestNarrativeLine(unittest.TestCase):
    def test_line_from_company_file(self):
        line = alpha_watch.narrative_line("co-vicor", today=date(2026, 10, 29))
        self.assertTrue(line.startswith("내러티브(확산"))
        self.assertIn("gap -1", line)
        self.assertNotIn("갱신 필요", line)

    def test_stale_and_missing(self):
        self.assertIn("갱신 필요", alpha_watch.narrative_line("co-vicor", today=date(2026, 12, 31)))
        self.assertIn("미작성", alpha_watch.narrative_line("co-없는종목"))


if __name__ == "__main__":
    unittest.main()
