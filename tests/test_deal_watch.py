"""딜 추적 문서철(radar/pollers/deal_watch.py) 오프라인 시험 — 2026-11-12 마스터 지시"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import common, deal_watch as dw  # noqa: E402


class TestDealWatch(unittest.TestCase):
    def setUp(self):
        self.d = (common.load_yaml("config/deal_watch.yaml") or {})["dossiers"][0]
        self.kw = re.compile(self.d["keywords"], re.I)

    def test_keywords(self):
        self.assertTrue(self.kw.search("Intel and SK hynix form joint venture"))
        self.assertTrue(self.kw.search("lease of the fab in New Albany"))
        self.assertFalse(self.kw.search("Mr. Brown, please lease the parking area"))   # 'please'·일반 임대 오탐
        self.assertFalse(self.kw.search("data:image/png;base64,QUFBSEJNQUFB"))

    def test_text_strips_encoded(self):
        raw = '<svg><polygon points="1 2"/></svg><script>var x="SK hynix"</script><p>Ordinance O-31-2026 tax abatement</p>' + "A" * 80
        t = dw._text(raw)
        self.assertNotIn("hynix", t)
        self.assertIn("Ordinance", t)
        self.assertNotIn("A" * 60, t)

    def test_expected_and_sources(self):
        types = {s["type"] for s in self.d["sources"]}
        self.assertTrue({"gn", "page", "swagit", "fedreg", "sec_fts"} <= types)
        self.assertGreaterEqual(len(self.d.get("expected") or []), 3)


if __name__ == "__main__":
    unittest.main()
