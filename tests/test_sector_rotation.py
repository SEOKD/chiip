"""섹터 순환 스크린·섹터 판단 틀 카드 시험 (마스터 지시 2026-11-13 종목 범위 확대 2단계, ADR-027)"""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
import sector_rotation as sr  # noqa: E402

C = {"per_run": 2, "limit": 30, "stale_days": 14, "filters": {}, "sort_by": "Perf.6M", "min_value_traded_usd": 5e6, "columns": [],
     "weights": {"growth": 0.30, "momentum": 0.25, "quality": 0.20, "size": 0.15, "value": 0.10}, "top_n": 3, "card_days": 90,
     "exclude_exchanges": ["OTC"],
     "rotation": {"A": ["가", "health", "health"], "B": ["나", "financials", "financials"], "C": ["다", "energy", "energy"]},
     "industry_group": [["Biotechnology", "biotech"]], "group_tv": {"biotech": "A"}}


def row(sym, g, perf, opm=10, mcap=2e9, vol=1e6, close=20):
    return {"symbol": sym, "name": sym.split(":")[-1], "description": sym, "industry": "Biotechnology", "market_cap_basic": mcap,
            "total_revenue_yoy_growth_ttm": g, "operating_margin_ttm": opm, "enterprise_value_to_revenue_ttm": 5, "Perf.6M": perf,
            "average_volume_30d_calc": vol, "close": close, "price_52_week_high": close * 1.05}


class Plan(unittest.TestCase):
    def setUp(self):
        self._p = sr.priority_sectors
        sr.priority_sectors = lambda c: []

    def tearDown(self):
        sr.priority_sectors = self._p

    def test_once_per_day_and_cursor(self):
        p = sr.plan(date(2026, 11, 13), C, {}, write=False)
        self.assertEqual(p["sectors"], ["A", "B"])
        st = {"cursor": 2, "last_date": "2026-11-13", "last_sectors": ["A", "B"]}
        self.assertFalse(sr.plan(date(2026, 11, 13), C, st, write=False)["due"])
        p = sr.plan(date(2026, 11, 16), C, st, write=False)
        self.assertEqual(p["sectors"], ["C", "A"])           # 한 바퀴 돌아 처음으로
        self.assertEqual(p["specs"][0]["filters"]["sector"], "C")

    def test_priority_first(self):
        sr.priority_sectors = lambda c: ["C"]
        self.assertEqual(sr.plan(date(2026, 11, 13), C, {}, write=False)["sectors"], ["C", "A"])


class Score(unittest.TestCase):
    def test_otc_and_liquidity_and_outlier(self):
        rows = [row("OTC:X", 50, 400), row("NASDAQ:LOW", 50, 100, vol=100), row("NASDAQ:A1", 40, 80), row("NASDAQ:A2", 20, 30),
                row("NASDAQ:A3", 30, 50, opm=-3000), row("NASDAQ:A4", 25, 40), row("NASDAQ:A5", 15, 20)]
        out = sr.score_sector({"sector": "A", "rows": rows}, C)
        tks = [r["ticker"] for r in out]
        self.assertNotIn("X", tks)
        self.assertNotIn("LOW", tks)
        self.assertEqual(len(out), 3)
        self.assertEqual(out[0]["ticker"], "A1")
        self.assertEqual(out[0]["group"], "biotech")
        self.assertEqual(out[0]["lens"], "health")


class Card(unittest.TestCase):
    def write(self, d, **kw):
        card = {"id": "us-abc", "ticker": "ABC", "lens": "health", "as_of": "2026-11-13", "answers": {i: "미확인" for i in range(1, 8)},
                "edge": 6.5, "evidence": ["https://www.sec.gov/x"], "kill": "3상 실패", "why": "요지"}
        card.update(kw)
        p = Path(d) / "c.yaml"
        import yaml
        p.write_text(yaml.safe_dump(card, allow_unicode=True), encoding="utf-8")
        return p

    def test_pass(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sr.card_check(self.write(d)), [])

    def test_fail_rules(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(any("URL" in e for e in sr.card_check(self.write(d, evidence=["10-K"]))))
            self.assertTrue(any("0~10" in e for e in sr.card_check(self.write(d, edge=12))))
            self.assertTrue(any("판단 틀" in e for e in sr.card_check(self.write(d, lens="nope"))))
            self.assertTrue(any("질문" in e for e in sr.card_check(self.write(d, answers={1: "x"}))))
            self.assertTrue(any("kill" in e for e in sr.card_check(self.write(d, kill=""))))

    def test_all_lenses_have_seven_questions(self):
        import re
        for f in (ROOT / "knowledge" / "methods" / "sector_lenses").glob("*.md"):
            if f.name == "README.md":
                continue
            self.assertEqual(len(re.findall(r"(?m)^\d+\. ", f.read_text(encoding="utf-8"))), 7, f.name)

    def test_edge_flows_to_screen_rows(self):
        with tempfile.TemporaryDirectory() as d:
            cards, cands = Path(d) / "cards", Path(d) / "c.json"
            cards.mkdir()
            self.write(cards, as_of=date.today().isoformat(), edge=7.5).rename(cards / "us-abc.yaml")
            cands.write_text(json.dumps({"sectors": {"A": {"name": "가", "rows": [{"ticker": "ABC", "name": "Abc", "score": 1.2, "rev_growth": 40,
                                                                                   "mcap_usd": 2e9, "industry": "Biotechnology"},
                                                                                  {"ticker": "DEF", "name": "Def", "score": 1.0, "rev_growth": 30,
                                                                                   "mcap_usd": 2e9, "industry": "Biotechnology"}]}}}), encoding="utf-8")
            o1, o2 = sr.CARDS, sr.CANDS
            sr.CARDS, sr.CANDS = cards, cands
            try:
                rows = {r["id"]: r for r in sr.rows_for_screen(set())}
            finally:
                sr.CARDS, sr.CANDS = o1, o2
            self.assertEqual(rows["us-abc"]["edge"], 7.5)
            self.assertEqual(rows["us-def"]["edge"], 5)
            self.assertEqual(rows["us-abc"]["rev_growth"], 0.4)


if __name__ == "__main__":
    unittest.main()
