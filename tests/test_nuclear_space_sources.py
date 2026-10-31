"""원자력·위성 정부 원천 시험 — 등록부·펄스 분류·판정 상향(2026-10-31)"""
import sys
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))

import promote  # noqa: E402
import pulse  # noqa: E402

IDS = ("src-nuclear-nrc", "src-nuclear-doe", "src-space-gov-gn")


def registry():
    d = yaml.safe_load((ROOT / "config" / "source_registry.yaml").read_text(encoding="utf-8"))
    rows = d if isinstance(d, list) else d.get("sources") or d
    return {r["id"]: r for r in rows}


class TestSources(unittest.TestCase):
    def test_registered_and_enabled(self):
        reg = registry()
        for i in IDS:
            self.assertTrue(reg[i]["enabled"] and reg[i]["terms_note"], i)
            self.assertEqual(reg[i]["method"], "rss")

    def test_pulse_class_keeps_documents_without_a_company(self):
        for i in IDS:
            self.assertEqual(pulse.class_of(i), "원자력·위성")
        self.assertTrue(pulse.relevant({"title": "NRC Issues Construction Permit", "language": "en"}, "원자력·위성"))

    def test_doe_filter_drops_other_energy_news(self):
        import re
        inc = re.compile(registry()["src-nuclear-doe"]["include_regex"], re.I)
        self.assertTrue(inc.search("DOE Awards HALEU Enrichment Task Orders"))
        self.assertIsNone(inc.search("DOE Announces Grid Resilience Funding"))


class TestXCitedSource(unittest.TestCase):
    def test_registered_as_news_index_only(self):
        src = registry()["src-x-cited-gn"]
        self.assertTrue(src["enabled"])
        self.assertEqual((src["method"], src["doc_type"], src["auth"]), ("rss", "SNS", "none"))
        self.assertTrue(all("on X" in q["q"] for q in src["feed_queries"]))
        self.assertFalse(registry()["src-research-x"].get("enabled"))


class TestRssExcludeAfterFailedFeed(unittest.TestCase):
    def test_exclude_regex_survives_a_failed_feed(self):   # except … as exc가 정규식 변수를 지우던 결함(2026-10-31)
        src = {"id": "src-x", "feed_urls": ["https://a", "https://b"], "exclude_regex": "Job", "language": "en", "doc_type": "규제·정책"}

        def get(url):
            if url.endswith("a"):
                raise OSError("x")
            return "b"
        row = {"title": "NRC issues permit", "link": "https://b/1", "date": "", "desc": ""}
        with mock.patch.object(pulse.rss.common, "http_get", get), mock.patch.object(pulse.rss, "parse_feed", lambda t: [row, {**row, "title": "Job posting", "link": "https://b/2"}]):
            items = pulse.rss.poll_source(src)
        self.assertEqual([i["title"] for i in items], ["NRC issues permit"])


class TestPromote(unittest.TestCase):
    def rule(self, title, sid, ents=()):
        with mock.patch.object(promote.common, "watch_theme_ids", return_value={"us-leu"}):
            return promote.ns_rule(title, title, sid, list(ents))

    def test_licensing_stage_and_contract(self):
        self.assertTrue(self.rule("NRC Issues Construction Permit for Kemmerer", "src-nuclear-nrc"))
        self.assertTrue(self.rule("SDA awards Tranche 3 contract", "src-space-gov-gn"))
        self.assertFalse(self.rule("NRC to Hold Webinar on contract", "src-nuclear-nrc"))
        self.assertFalse(self.rule("Centrus wins contract", "src-rss", ["us-leu"]))                         # 금액 없음
        self.assertTrue(self.rule("Centrus wins $900 million contract", "src-rss", ["us-leu"]))


if __name__ == "__main__":
    unittest.main()
