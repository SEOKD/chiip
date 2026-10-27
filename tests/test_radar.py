"""레이더·검사 스크립트 오프라인 테스트 (네트워크·키 불필요)

실행: py -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts"))

from pollers import common, rss  # noqa: E402


class TestCommon(unittest.TestCase):
    def test_match_entities_korean_and_english(self):
        self.assertIn("co-skhynix", common.match_entities("SK하이닉스, HBM4 양산"))
        self.assertIn("co-skhynix", common.match_entities("SK hynix ships HBM4"))
        self.assertIn("co-lotteem", common.match_entities("일진머티리얼즈 동박"))

    def test_make_item_shape(self):
        it = common.make_item("src-x", "1", "https://e.com/a", "삼성전자 HBM4 공급", "2026-10-27", "기사", "ko")
        for key in ("item_id", "source_id", "url", "title", "published_at", "detected_at",
                    "entities_matched", "keywords_matched", "doc_type", "language", "snippet",
                    "content_hash", "event_cluster"):
            self.assertIn(key, it)
        self.assertIn("co-samsung", it["entities_matched"])
        self.assertIn("HBM4", it["keywords_matched"])

    def test_interval_for(self):
        tz = common.KST
        self.assertEqual(common.interval_for("T0", datetime(2026, 10, 27, 10, 0, tzinfo=tz)), 5)   # 화요일 장중
        self.assertEqual(common.interval_for("T0", datetime(2026, 10, 27, 2, 0, tzinfo=tz)), 30)   # 새벽
        self.assertEqual(common.interval_for("T0", datetime(2026, 10, 31, 10, 0, tzinfo=tz)), 60)  # 토요일


class TestRss(unittest.TestCase):
    def test_parse_rss_and_atom(self):
        rss_xml = b"<rss><channel><item><title>A</title><link>https://a</link><pubDate>Tue, 27 Oct 2026 01:00:00 GMT</pubDate></item></channel></rss>"
        atom_xml = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>B</title><link href="https://b"/><updated>2026-10-27T01:00:00Z</updated></entry></feed>'
        self.assertEqual(rss.parse_feed(rss_xml)[0]["link"], "https://a")
        self.assertEqual(rss.parse_feed(atom_xml)[0]["link"], "https://b")
        self.assertTrue(rss.to_iso("Tue, 27 Oct 2026 01:00:00 GMT").startswith("2026-10-27T01:00"))


class TestDeterministicP0(unittest.TestCase):
    def test_rule_matches_and_excludes(self):
        import run_poll
        sent_texts = []
        orig = run_poll.notify.send
        run_poll.notify.send = lambda text, level="P1": sent_texts.append(text) or True
        orig_save = common.save_state
        common.save_state = lambda name, data: None
        try:
            items = [
                {"item_id": "src-dart:1", "source_id": "src-dart", "tier": "T0", "title": "SK하이닉스 단일판매ㆍ공급계약체결",
                 "report_nm": "단일판매ㆍ공급계약체결", "url": "u1"},
                {"item_id": "src-dart:2", "source_id": "src-dart", "tier": "T0", "title": "정정",
                 "report_nm": "[기재정정]단일판매ㆍ공급계약체결", "url": "u2"},
                {"item_id": "src-dart:3", "source_id": "src-dart", "tier": "candidate", "title": "T1",
                 "report_nm": "단일판매ㆍ공급계약체결", "url": "u3"},
            ]
            sent = run_poll.deterministic_p0(items)
        finally:
            run_poll.notify.send = orig
            common.save_state = orig_save
        self.assertEqual(sent, ["src-dart:1"])
        self.assertTrue(sent_texts[0].startswith("[P0-규칙]"))


class TestNotifyGuard(unittest.TestCase):
    def test_guard_blocks_embargo_marker(self):
        import notify
        self.assertIsNotNone(notify.guard("[EMBARGO] 내용"))
        self.assertIsNone(notify.guard("평범한 알림"))


class TestValidators(unittest.TestCase):
    def test_claims_pass(self):
        import validate_claims
        self.assertEqual(validate_claims.main([]), 0)

    def test_scan_detects_token(self):
        import scan_sealed
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "leak.md"
            fake = "123456789" + ":" + "Ab" * 17 + "c"   # 실행 중 조합(파일엔 토큰 모양이 없도록)
            p.write_text(f"bot {fake}\n", encoding="utf-8")
            hits = scan_sealed.scan(p, [])
        self.assertTrue(any("텔레그램" in h for h in hits))


class TestModelCalc(unittest.TestCase):
    def test_driver_math_and_scenario(self):
        import model_calc as m
        rows = [{"period": "2027Q1", "segment": "A", "driver": d, "value": v} for d, v in
                [("volume", "10"), ("asp", "5"), ("asp@bull", "6"), ("cogs_per_unit", "2")]]
        rows += [{"period": "2027Q1", "segment": "전사", "driver": d, "value": v} for d, v in
                 [("opex", "10"), ("tax_rate", "0.2"), ("da", "3"), ("capex", "4")]]
        base = m.compute(m.pick(rows, "기본"))[-1]
        bull = m.compute(m.pick(rows, "bull"))[-1]
        self.assertEqual(base["revenue"], 50)
        self.assertEqual(base["operating_profit"], 20)
        self.assertAlmostEqual(base["fcf"], 15)
        self.assertEqual(bull["revenue"], 60)


class TestTriangulate(unittest.TestCase):
    def test_convergence_and_origin_dedupe(self):
        import triangulate as t
        rules = {"weights": {"S1": 1, "S2": 3, "S3": 8, "S4": 20}}
        sigs = [{"id": "a", "strength": "S2", "layer": "L1", "origin_id": "o1"},
                {"id": "b", "strength": "S2", "layer": "L6", "origin_id": "o2"},
                {"id": "c", "strength": "S2", "layer": "L6", "origin_id": "o2"}]  # 재인용 — 하나로
        r = t.assess(sigs, rules)
        self.assertEqual(r["independent"], 2)
        self.assertEqual(r["alert"], "수렴경보→P1")
        self.assertEqual(t.assess([{"id": "x", "strength": "S4", "layer": "L1"}], rules)["alert"], "단독경보(S4+)→P0")


class TestPressWire(unittest.TestCase):
    def setUp(self):
        from pollers import press_wire
        self.p = press_wire
        self.cfg = press_wire._cfg()

    def entry(self, title, desc):
        return {"title": title, "desc": desc, "link": "https://example.com/x", "date": ""}

    def test_listing_regions(self):
        self.assertEqual(self.p.listing("Foo (NASDAQ: FOO) today", self.cfg), (["US"], "NASDAQ: FOO"))
        self.assertEqual(self.p.listing("Baz (KRX: 000660) said", self.cfg)[0], ["KR"])
        self.assertEqual(self.p.listing("Acme (Euronext Paris: ACM)", self.cfg)[0], ["EU"])
        self.assertEqual(self.p.listing("Private Co. announced", self.cfg), ([], None))

    def test_classify(self):
        sector = {"sector_feed": True}
        general = {"sector_feed": False}
        r = self.p.classify(self.entry("Foo Announces Definitive Agreement to Acquire Bar", "Foo (NASDAQ: FOO) today"), sector, self.cfg)
        self.assertEqual(r[2], ["mna"])
        # 일반 피드는 분야 표현이 있어야 통과
        self.assertIsNone(self.p.classify(self.entry("Bank Reports Q3 Results", "Bank (NYSE: BNK) today"), general, self.cfg))
        self.assertIsNotNone(self.p.classify(self.entry("Chipco Reports Q3 Results", "Chipco (NASDAQ: CHP), a semiconductor maker"), general, self.cfg))
        # 비상장·로펌 광고·번역판 제외
        self.assertIsNone(self.p.classify(self.entry("Startup Launches GPU Cloud", "Startup Inc. today"), sector, self.cfg))
        self.assertIsNone(self.p.classify(self.entry("FOO Investors Have Opportunity to Lead Securities Fraud Lawsuit", "(NASDAQ: FOO)"), sector, self.cfg))
        self.assertIsNone(self.p.classify(self.entry("Foo gewinnt Grossauftrag für Chips", "Foo (SIX: FOO)"), sector, self.cfg))


class TestWeeklyMovers(unittest.TestCase):
    def test_pick_filters_and_converts(self):
        from markets import weekly_movers as wm
        cfg = {"exclude_name_pattern": r"\bETF\b|우선주", "min_avg_volume_200d": 1000}
        rates = {"USD": 1, "KRW": 1400}
        rows = [
            {"name": "Big Gainer Inc", "code": "BIG", "exchange": "US", "currency_symbol": "USD", "refund_5d_p": 30.4,
             "market_capitalization": 2e10, "sector": "Technology", "industry": "Software", "avgvol_200d": 5e5},
            {"name": "Some ETF", "code": "ETF1", "currency_symbol": "USD", "refund_5d_p": 50, "market_capitalization": 5e10,
             "sector": "Fund", "avgvol_200d": 5e5},
            {"name": "Tiny Co", "code": "TNY", "currency_symbol": "USD", "refund_5d_p": 40, "market_capitalization": 5e8,
             "sector": "Tech", "avgvol_200d": 5e5},
            {"name": "No Sector Fund", "code": "NSF", "currency_symbol": "USD", "refund_5d_p": 45, "market_capitalization": 3e10,
             "avgvol_200d": 5e5},
            {"name": "Big Gainer Inc", "code": "BIG2", "currency_symbol": "USD", "refund_5d_p": 29, "market_capitalization": 2e10,
             "sector": "Technology", "avgvol_200d": 5e5},
        ]
        out = wm.pick(rows, {"count": 5, "market_cap_usd_min": 1e10}, cfg, rates)
        self.assertEqual([r["ticker"] for r in out], ["BIG"])
        kr = [{"name": "삼현", "code": "437730", "currency_symbol": "KRW", "refund_5d_p": 13.2,
               "market_capitalization": 4e11, "sector": "Industrials", "avgvol_200d": 2e5}]
        self.assertEqual(wm.pick(kr, {"count": 10, "market_cap_usd_min": 2e8}, cfg, rates)[0]["market_cap_usd"], round(4e11 / 1400))

    def test_collect_waits_outside_window(self):
        from markets import weekly_movers as wm
        if common.now_kst().weekday() != 5:
            self.assertEqual(wm.collect(), (0, 0))


if __name__ == "__main__":
    unittest.main()
