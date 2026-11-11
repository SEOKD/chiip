"""협업사 채용 공고 — 단어 경계·계열사 제외·상용구(2026-11-11 마스터 지시 '대안 만들어')"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar" / "talent" / "collectors"))
import jobs_boards as jb  # noqa: E402

CFG = {"partner_terms": {"co-samsung": ["Samsung", "SF2P?\+?"]}}
LEX = {"co-samsung": {"names": ["SEC", "Samsung Electronics"]}}


class T(unittest.TestCase):
    def test_word_boundary_and_acronym(self):
        pat = jb.patterns(CFG, LEX)["co-samsung"]
        self.assertIsNone(pat.search("security engineer, SEC filings"))   # 'SEC' 약어 제외
        self.assertIsNotNone(pat.search("experience on TSMC or Samsung 2nm"))
        self.assertIsNotNone(pat.search("tape-out on SF2P"))
        self.assertIsNone(pat.search("ASF2 module"))


if __name__ == "__main__":
    unittest.main()
