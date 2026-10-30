"""치입 → Chiip 표기가 낱말만 바꾸는지 시험 (2026-10-30 '8년치입니다' → '8년Chiip니다' 깨짐)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))

import notify  # noqa: E402
from units import chiip_name  # noqa: E402


class TestChiipName(unittest.TestCase):
    def test_word_is_replaced(self):
        for a, b in (("치입 판단", "Chiip 판단"), ("[치입 펄스]", "[Chiip 펄스]"), ("치입은 본다", "Chiip은 본다"), ("(치입 계산)", "(Chiip 계산)")):
            self.assertEqual(chiip_name(a), b)

    def test_ordinary_korean_is_untouched(self):
        for s in ("잔고는 매출의 8년치입니다.", "8년 치입니다", "이것이 가치입니다", "위치입니다", "수치입력", "조치입니다"):
            self.assertEqual(chiip_name(s), s)

    def test_notify_brand_keeps_sentence(self):
        self.assertIn("8년치입니다", notify.brand("잔고는 매출의 8년치입니다."))


if __name__ == "__main__":
    unittest.main()
