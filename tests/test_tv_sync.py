"""TradingView 동기화 시험 — 섹션 분해·위치 지정·재추가 금지(2026-10-31)"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))

import tv_sync as t  # noqa: E402

LIST = ["NYSE:GE", "###NUCLEAR", "NYSE:LEU", "###SPACE", "NYSE:PL", "###NONE"]


class TestParse(unittest.TestCase):
    def test_only_equities(self):
        for s in ("###SPACE", "KRX:000660/FX_IDC:USDKRW", "ICEEUR:G1!", "FRED:SOFR-ECONOMICS:USINTR+0.25"):
            self.assertFalse(t.is_equity(s), s)
        self.assertTrue(t.is_equity("LSE:BA."))

    def test_sections_and_hidden_character(self):
        self.assertEqual(t.sections(["NYSE:GE", "###⁤ELECTRIFICATION", "NYSE:ETN"]), [("", ["NYSE:GE"]), ("ELECTRIFICATION", ["NYSE:ETN"])])

    def test_alias_names_drop_short_forms(self):
        self.assertEqual(t.alias_names("Visa Inc."), ["Visa Inc."])
        self.assertEqual(t.alias_names("Cisco Systems, Inc."), ["Cisco Systems, Inc.", "Cisco Systems"])

    def test_sector(self):
        self.assertEqual(t.sector_of("NUCLEAR"), "nuclear")
        self.assertEqual(t.sector_of("SPACE"), "space")
        self.assertEqual(t.sector_of("HOTELS"), "other")


class TestMapping(unittest.TestCase):
    def test_same_code_on_different_markets_are_different_companies(self):
        code_id = {"BA": {"us": "us-ba", "eu": "gb-bae"}, "CCJ": {"us": "us-ccj"}, "000660": {"kr": "co-skhynix"}}
        c = {"exchange_market": {"NYSE": "us", "LSE": "eu", "BCBA": "other", "KRX": "kr"}}
        self.assertEqual(t.lookup(code_id, "NYSE:BA", c), "us-ba")
        self.assertEqual(t.lookup(code_id, "LSE:BA.", c), "gb-bae")
        self.assertEqual(t.lookup(code_id, "BCBA:CCJ", c), "us-ccj")          # 제3시장 상장은 미국 상장과 잇는다
        self.assertIsNone(t.lookup({"T": {"us": "us-t"}}, "LSE:T", c))        # 영국 T는 AT&T가 아니다
        self.assertEqual(t.lookup(code_id, "KRX:000660", c), "co-skhynix")

    def test_code_market(self):
        self.assertEqual(t.code_market("BA.LSE"), "eu")
        self.assertEqual(t.code_market("NVDA.US"), "us")
        self.assertEqual(t.code_market("000660", "KRX"), "kr")
        self.assertEqual(t.code_market("6976", "jp"), "jp")


class TestPlanOrder(unittest.TestCase):
    def test_insert_in_section_keeps_everything_after_it(self):
        order, full = t.plan_order(LIST, [("###NUCLEAR", ["NYSE:CCJ"])])
        self.assertEqual(order, ["NYSE:CCJ", "###SPACE", "NYSE:PL", "###NONE"])
        self.assertEqual(full, ["NYSE:GE", "###NUCLEAR", "NYSE:LEU", "NYSE:CCJ", "###SPACE", "NYSE:PL", "###NONE"])

    def test_new_section_goes_before_none(self):
        order, full = t.plan_order(LIST, [("###DEFENSE", ["NYSE:NPK"])])
        self.assertEqual(order, ["###DEFENSE", "NYSE:NPK", "###NONE"])
        self.assertEqual(full[-3:], ["###DEFENSE", "NYSE:NPK", "###NONE"])

    def test_no_none_appends(self):
        order, full = t.plan_order(["TSE:6702"], [("###DEFENSE", ["TSE:7721"])])
        self.assertEqual(order, ["###DEFENSE", "TSE:7721"])
        self.assertEqual(full, ["TSE:6702", "###DEFENSE", "TSE:7721"])

    def test_several_inserts_produce_same_result_as_api(self):
        order, full = t.plan_order(LIST, [("###SPACE", ["NYSE:RKLB"]), ("###NUCLEAR", ["NYSE:CCJ"])])
        api = [s for s in LIST if s not in order] + order     # add는 이미 있는 항목을 맨 뒤로 옮긴다
        self.assertEqual(api, full)


class TestPlan(unittest.TestCase):
    def test_master_removal_is_not_added_back(self):
        snap = {"watchlists": [{"id": 1, "name": "1_US", "symbols": ["NYSE:GE", "###NONE"]}]}
        c = {"folders": {"1_US": {"market": "us"}}, "exchange_market": {"NYSE": "us"}, "theme_sections": {"t": "###NUCLEAR"}}
        rows = {"NYSE:GE": {"entity_id": "us-ge"}, "NYSE:CCJ": {"entity_id": "us-ccj"}, "NYSE:LEU": {"entity_id": "us-leu"}}
        with tempfile.TemporaryDirectory() as tmp:
            snap_p = Path(tmp) / "s.json"
            snap_p.write_text(json.dumps(snap), encoding="utf-8")
            with patch.object(t, "SNAP", snap_p), patch.object(t, "cfg", lambda: c), patch.object(t, "load_symbols", lambda: rows), \
                    patch.object(t, "added_ledger", lambda: [{"entity_id": "us-ccj"}]), patch.object(t, "chiip_picks", lambda: {"us-ccj": "t", "us-leu": "t", "us-x": "t"}), \
                    patch.object(t, "known_entities", lambda: ({}, {"us-x": {"name": "X"}})):
                p = t.plan()
        self.assertEqual(p["removed_by_master"], ["us-ccj"])
        self.assertEqual(p["need_symbol"], [{"id": "us-x", "name": "X", "theme": "t"}])
        self.assertEqual(p["calls"], [{"folder": "1_US", "watchlist_id": "1", "symbols": ["###NUCLEAR", "NYSE:LEU", "###NONE"], "new": 1}])


class TestDiscoveryBlock(unittest.TestCase):
    def test_generated_themes_load_and_have_no_duplicates(self):
        import yaml
        d = yaml.safe_load((ROOT / "config" / "discovery.yaml").read_text(encoding="utf-8"))
        tv = [x for x in d["themes"] if x.get("source") == "tradingview"]
        self.assertTrue(tv)
        ids = [c["id"] for x in d["themes"] for c in x["candidates"]]
        self.assertEqual(len(ids), len(set(ids)))
        codes = {c["code"] for x in tv for c in x["candidates"]}
        self.assertNotIn("MYR", codes)    # 오기로 보이는 항목은 뺀다


if __name__ == "__main__":
    unittest.main()
