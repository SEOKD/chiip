"""Informations 새 정보만 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import notion_state as ns  # noqa: E402


class TestFresh(unittest.TestCase):
    def test_only_new_lines(self):
        st = {"pages": {}}
        old = "# 제목\n- HBM 계약 A\n- 정책 B\n---"
        new, had = ns.fresh("p", old, st)
        self.assertFalse(had)
        self.assertEqual(len(new), 3)
        ns.remember("p", old, st)
        new, had = ns.fresh("p", old + "\n- 새 소식 C", st)
        self.assertTrue(had)
        self.assertEqual(new, ["- 새 소식 C"])
        self.assertEqual(ns.fresh("p", "  - HBM   계약 A", st)[0], [])   # 공백·글머리만 바뀐 줄은 새 정보가 아니다


if __name__ == "__main__":
    unittest.main()
