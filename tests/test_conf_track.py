"""학회 참여 추적 소속 매칭·채점 (ADR-015)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import conf_track as ct  # noqa: E402

ORGS = ct.yml(ct.ORGS)


def work(affs, title="A 24Gb 10.5Gbps DRAM", first=0, topic="DRAM"):
    return {"id": "https://openalex.org/W1", "doi": None, "title": title, "publication_date": "2025-02-16", "primary_topic": {"display_name": topic},
            "authorships": [{"author_position": "first" if i == first else "middle", "author": {"display_name": "홍길동"},
                             "institutions": [{"display_name": a}] if a.startswith("!") is False else [], "raw_affiliation_strings": [a.lstrip("!")]} for i, a in enumerate(affs)]}


class TestMatch(unittest.TestCase):
    def test_units_and_first_author(self):
        r = ct.match(work(["Samsung Electronics (South Korea)", "SK Hynix (South Korea)", "NVIDIA (United States)"]), ORGS)
        self.assertEqual(r["groups"], ["samsung", "sk"])
        self.assertEqual(r["role"], "제1저자")
        self.assertEqual(r["conf"], "A")
        self.assertIn("NVIDIA", r["partners"])
        self.assertTrue(r["numbers"])

    def test_raw_only_is_B_and_exclusions(self):
        self.assertEqual(ct.match(work(["!SK hynix, Icheon, Korea"]), ORGS)["conf"], "B")
        self.assertIsNone(ct.match(work(["Samsung Medical Center", "Seoul National University"]), ORGS))

    def test_short_token_needs_word(self):
        self.assertIsNone(ct.unit_of("SKKU Sungkyunkwan", ORGS))
        self.assertIsNone(ct.unit_of("BLGroup Inc", ORGS))

    def test_no_author_names_stored(self):
        r = ct.match(work(["Samsung Electronics"]), ORGS)
        self.assertNotIn("홍길동", str(r))

    def test_score_rival_and_new_topic(self):
        r = ct.match(work(["Samsung Electronics"]), ORGS)
        s, why = ct.score(r, set(), {"DRAM": {"Micron"}}, ct.yml(ct.PIPE)["weights"])
        self.assertGreaterEqual(s, 4.0)
        self.assertTrue(any("Micron" in w for w in why))


if __name__ == "__main__":
    unittest.main()
