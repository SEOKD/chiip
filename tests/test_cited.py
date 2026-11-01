"""기사 인용 컨센서스 장부 (마스터 지시 2026-11-01)"""
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "fiscal"))
import cited  # noqa: E402

BASE = {"ticker": "AMD", "period": "2026Q3", "metric": "EPS", "value": 2.07, "unit": "$", "basis": "조정", "vendor": "LSEG", "outlet": "CNBC",
        "url": "https://www.cnbc.com/a", "published": "2026-11-03T10:00:00-05:00", "route": "websearch"}


class TestCited(unittest.TestCase):
    def test_source_fields_are_required(self):
        rows, _, bad = cited.merge([{**BASE, "url": ""}, {**BASE, "published": "어제"}, {**BASE, "vendor": "블로그"}], [], "2026-11-01")
        self.assertEqual(rows, [])
        self.assertEqual(len(bad), 3)

    def test_recitation_is_not_independent(self):
        rows, again, _ = cited.merge([BASE, {**BASE, "outlet": "Yahoo", "url": "https://x.example/b"}], [], "2026-11-01")
        self.assertEqual(again, 1)
        self.assertEqual(rows[0]["origin_id"], rows[1]["origin_id"])
        self.assertEqual(cited.independent(rows, "AMD", "2026Q3", "EPS"), 1)

    def test_same_article_is_skipped(self):
        first, _, _ = cited.merge([BASE], [], "2026-11-01")
        again, _, _ = cited.merge([BASE], first, "2026-11-02")
        self.assertEqual(again, [])

    def test_vendors_stay_side_by_side(self):
        rows, _, _ = cited.merge([BASE, {**BASE, "vendor": "FactSet", "value": 2.1, "url": "https://x.example/c"}], [], "2026-11-01")
        got = cited.latest(rows, "AMD", "2026Q3")
        self.assertEqual(sorted(k[1] for k in got), ["FactSet", "LSEG"])
        self.assertEqual(cited.independent(rows, "AMD", "2026Q3", "EPS"), 2)

    def test_only_pre_release_values_with_before(self):
        rows, _, _ = cited.merge([BASE, {**BASE, "value": 2.2, "url": "https://x.example/d", "published": "2026-11-05"}], [], "2026-11-01")
        self.assertEqual(float(cited.latest(rows, "AMD", "2026Q3", "2026-11-04")[("EPS", "LSEG")]["value"]), 2.07)
        self.assertEqual(float(cited.latest(rows, "AMD", "2026Q3")[("EPS", "LSEG")]["value"]), 2.2)

    def test_queue_starts_with_uncovered(self):
        self.assertEqual(cited.queue([{"ticker": "AMD"}], ["NASDAQ_AMD", "NYSE_ANET"], 2), ["ANET", "AMD"])

    def test_stale_checks(self):
        self.assertEqual(cited.stale([{"name": "a", "checked": "2026-09-01"}, {"name": "b", "checked": "2026-10-20"}], date(2026, 11, 1), 30), ["a"])

    def test_cited_values_stay_out_of_est(self):
        self.assertFalse(cited.config()["use_in_est"])

    def test_blocked_channels_are_not_opened(self):
        names = {c["name"]: c["status"] for c in cited.config()["channels"]}
        for n in ("CNBC", "Investing.com", "Reuters", "Seeking Alpha"):
            self.assertEqual(names[n], "blocked")


if __name__ == "__main__":
    unittest.main()
