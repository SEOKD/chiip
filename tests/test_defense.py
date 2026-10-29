"""방위 섹터·시가총액 구간 엔진 시험 (마스터 지시 2026-10-29 — "Ten-bagger와 Pulse에 방위 섹터", "$1B~$10B … $200B 이상 구간별로 나눠 접근")"""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))

import bands  # noqa: E402
import promote  # noqa: E402
import pulse  # noqa: E402
from pollers import common, gate, rss  # noqa: E402


def _y(p):
    return yaml.safe_load((ROOT / p).read_text(encoding="utf-8"))


class TestDefenseMap(unittest.TestCase):
    def test_map_is_valid(self):
        d = _y("config/defense.yaml")
        ids = [c["id"] for c in d["companies"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(d["segments"]), {"prime", "product", "services", "solutions"})
        self.assertEqual(len(d["products"]), 10)   # 제품 대분류 10개
        for c in d["companies"]:
            self.assertTrue(set(c.get("products") or []) <= set(d["products"]), c["id"])
            self.assertTrue(set(c["segments"]) <= set(d["segments"]), c["id"])
            if c["listed"]:
                self.assertTrue(c.get("code"), c["id"])
        countries = {c["country"] for c in d["companies"]}
        self.assertTrue({"DE", "FR", "IT", "ES", "JP", "US"} <= countries)

    def test_aliases_match_and_avoid_false_positives(self):
        common._ALIAS_CACHE = None
        self.assertIn("de-rheinmetall", common.match_entities("Rheinmetall wins Bundeswehr ammunition order"))
        self.assertIn("it-leonardo", common.match_entities("Leonardo S.p.A. reports nine-month results"))
        self.assertNotIn("us-saic", common.match_entities("SAIC Motor recalls vehicles in China"))   # 상하이차와 겹치는 약칭 제거
        self.assertNotIn("es-indra", common.match_entities("Indra Nooyi joins board"))

    def test_gate_tracks_defense(self):
        gate._CACHE.pop("extra_focus", None)
        self.assertIn("de-hensoldt", gate.extra_focus())

    def test_company_line_and_ticker(self):
        import notify
        notify._LINES.clear()
        self.assertIn("탄약", notify.company_line(["de-rheinmetall"]))
        self.assertEqual(notify.stock_label(["de-rheinmetall"]), "Rheinmetall(RHM)")


class TestDefenseRadar(unittest.TestCase):
    def test_rss_dict_query_and_domain_entities(self):
        src = {"feed_queries": [{"q": "site:bmvg.de when:2d", "hl": "de", "gl": "DE"}], "hl": "en-US", "gl": "US",
               "domain_entities": {"rheinmetall.com": "de-rheinmetall"}}
        urls = list(rss.feed_urls(src))
        self.assertIn("hl=de", urls[0][0])
        self.assertIn("gl=DE", urls[0][0])
        self.assertEqual(urls[1][1], "de-rheinmetall")   # 도메인 질의는 그 회사로 귀속

    def test_rss_exclude_and_min_words(self):
        entries = [{"link": "https://x/1", "title": "Sales Expert (m/f/d) - Rheinmetall", "desc": "", "date": "Wed, 29 Oct 2026 08:00:00 GMT"},
                   {"link": "https://x/2", "title": "- Rheinmetall", "desc": "", "date": "Wed, 29 Oct 2026 08:00:00 GMT"},
                   {"link": "https://x/3", "title": "Schakal infantry fighting vehicles for the Bundeswehr - Rheinmetall", "desc": "",
                    "date": "Wed, 29 Oct 2026 08:00:00 GMT"}]
        src = {"id": "src-defense-newsroom-gn", "domain_entities": {"rheinmetall.com": "de-rheinmetall"}, "exclude_regex": r"\((m|w|f)/(m|w|f)/d\)",
               "min_title_words": 5, "doc_type": "보도자료", "language": "en"}
        with patch.object(rss, "parse_feed", return_value=entries), patch.object(common, "http_get", return_value=b""):
            items = rss.poll_source(src)
        self.assertEqual(len(items), 1)   # 직무 페이지·빈 제목은 빠진다
        self.assertIn("de-rheinmetall", items[0]["entities_matched"])

    def test_pulse_defense_class(self):
        self.assertEqual(pulse.class_of("src-defense-gov-gn"), "방위")
        self.assertEqual(pulse.class_of("src-defense-newsroom-gn"), "방위")
        self.assertTrue(pulse.relevant({"language": "de", "title": "Rahmenvertrag für Munition"}, "방위"))   # 원문 언어 예외

    def test_promote_defense_rules(self):
        base = {"source_id": "src-defense-newsroom-gn", "entities_matched": ["de-rheinmetall"]}
        self.assertIsNotNone(promote.match({**base, "title": "Rheinmetall wins framework contract for 155mm ammunition - Rheinmetall"}))
        self.assertIsNone(promote.match({**base, "title": "Rheinmetall at Talent transfair: meet our engineers - Rheinmetall"}))
        self.assertIsNone(promote.match({**base, "title": "Fincantieri Conference call invitation 9M 2026 - Fincantieri", "entities_matched": ["it-fincantieri"]}))
        r = promote.match({"source_id": "src-defense-gov-gn", "entities_matched": [], "title": "DSCA 26-40 | Germany – PAC-3 MSE Missiles"})
        self.assertEqual(r[0], "규칙 상향: 미 대외군사판매 통보")
        # 방위 원천 밖(보도자료 배포처)은 10억 달러 이상 계약만
        prn = {"source_id": "src-prn", "entities_matched": ["us-ktos"]}
        self.assertIsNone(promote.match({**prn, "title": "Kratos awarded $12 million contract"}))
        self.assertIsNotNone(promote.match({**prn, "title": "Kratos awarded $1.2 billion contract for drones"}))


class TestBands(unittest.TestCase):
    def setUp(self):
        self.bl = bands.cfg()["list"]

    def test_band_boundaries(self):
        ids = [b["id"] for b in self.bl]
        self.assertEqual(ids, [f"B{i}" for i in range(12)])
        for prev, nxt in zip(self.bl, self.bl[1:]):   # 구간이 끊기지 않는다(B6 $50~60B 포함)
            self.assertEqual(prev["max_usd"], nxt["min_usd"])
        self.assertEqual(bands.band_of(5e9, self.bl)["id"], "B1")
        self.assertEqual(bands.band_of(1e10, self.bl)["id"], "B2")   # 경계값은 위 구간
        self.assertEqual(bands.band_of(5.5e10, self.bl)["id"], "B6")
        self.assertEqual(bands.band_of(3e12, self.bl)["id"], "B11")
        self.assertIsNone(bands.band_of(5e7, self.bl))

    def test_band_relative_score(self):
        factors = {"growth_accel": {"weight": 1.0, "direction": "high"}, "size": {"weight": 1.0, "direction": "low"}}
        rows = [{"id": "a", "fv": {"growth_accel": 0.5, "size": 2e9}}, {"id": "b", "fv": {"growth_accel": 0.1, "size": 8e9}},
                {"id": "c", "fv": {"growth_accel": None, "size": 5e9}}]
        s = bands.score_band(rows, factors)
        self.assertGreater(s["a"][0], s["b"][0])
        self.assertIn("growth_accel", s["c"][1])   # 빠진 자료 표시

    def test_tenx_arithmetic(self):
        t = bands.tenx({"mcap_usd": 1.0e11, "rev_ttm_usd": 5.0e10}, "defense", (5, 10), max_cap=5e12)
        self.assertAlmostEqual(t["target_usd"], 1e12)
        self.assertAlmostEqual(t["need_rev_usd"], 1e12 / 2.0)
        self.assertAlmostEqual(t["rev_cagr"][10], 10 ** 0.1 - 1, places=6)
        self.assertAlmostEqual(t["price_cagr"][5], 10 ** 0.2 - 1, places=6)
        self.assertEqual(t["verdict"], "도전적")   # 필요 매출 5,000억$ = 세계 군사비의 18%
        small = bands.tenx({"mcap_usd": 2e9, "rev_ttm_usd": 1e9}, "defense", (10,), max_cap=5e12)
        self.assertEqual(small["verdict"], "산술상 가능 영역")

    def test_ingest_profile_converts_currency(self):
        fx = bands.ecb_rates("<Cube currency='USD' rate='1.10'/><Cube currency='JPY' rate='170.0'/>")
        rec = bands.ingest_profile("jp-x", {"data": {"currency": "JPY", "market_cap": 1.7e12, "revenue": 3.4e11, "free_cash_flow": 1.7e10,
                                                      "pb_ratio": 2.0, "operating_margin": 0.1}}, fx, date(2026, 10, 29))
        self.assertAlmostEqual(rec["mcap_usd"], 1.7e12 * 1.10 / 170.0)
        self.assertAlmostEqual(rec["fcf_yield"], 0.01)
        miss = bands.ingest_profile("tw-x", {"currency": "TWD", "market_cap": 1e11}, fx)
        self.assertIsNone(miss["mcap_usd"])   # ECB에 없는 통화 → 환산 불가 표시
        self.assertIn("환율 없음", miss["note"])

    def test_universe_covers_sectors_and_tickers(self):
        u = bands.universe()
        secs = {r["sector"] for r in u.values()}
        self.assertTrue({"semis", "ai_hw", "software", "defense"} <= secs)
        self.assertEqual(bands.ticker_of(u["de-rheinmetall"]), ("RHM", "eu"))
        self.assertEqual(bands.resolve_id("ALAB", u), "co-asteralabs")   # 같은 회사는 감시 목록 id로


if __name__ == "__main__":
    unittest.main()
