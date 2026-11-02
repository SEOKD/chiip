"""로비 내역 결론 규칙 (마스터 지시 2026-11-03)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar" / "usgov"))
import lobby_watch as lw  # noqa: E402


class TestVerdict(unittest.TestCase):
    def test_no_lda_is_unknown_even_with_other_hits(self):
        self.assertEqual(lw.verdict({"lda": {"status": "키 없음", "rows": []}}), "미확인")

    def test_lda_result(self):
        self.assertEqual(lw.verdict({"lda": {"status": "ok", "rows": [{}]}}), "로비 등록 있음")
        self.assertIn("없음", lw.verdict({"lda": {"status": "ok", "rows": []}}))


if __name__ == "__main__":
    unittest.main()
