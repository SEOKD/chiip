"""협업 흔적 질의 구성(2026-11-11)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import partner_trace as pt  # noqa: E402

CFG = {"partners": [{"id": "eda", "sites": ["a.com", "b.com"], "why": "w"}], "entity_terms": {"co-samsung": '"Samsung Foundry"'},
       "claims": [{"id": "c1", "entity": "co-samsung", "q": "Meta Samsung", "why": "x"}]}


class T(unittest.TestCase):
    def test_queries(self):
        q = pt.queries(CFG)
        self.assertEqual(q[0][1], '("Samsung Foundry") (site:a.com OR site:b.com)')
        self.assertEqual(q[1][0], "claim:c1")


if __name__ == "__main__":
    unittest.main()
