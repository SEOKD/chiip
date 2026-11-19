"""Proviser 텔레그램 — 핵심 3개와 나머지 사이 빈 줄 정확히 하나(마스터 지시 2026-11-19)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "proviser"))
import tg_format as F  # noqa: E402


class TgFormat(unittest.TestCase):
    def test_one_break(self):
        t = "[Chiip Proviser 2026-11-19]\n\n* Pulse 9.3(+0.1)\n* Analysis 8.3(-0.4)\n* Portfolio 8.7(+0.1)\n\n\n* Weekly 3.0(+0.0)\n\n* Model Lab 8.2(+0.0)\n\n18개 7일 평균 8.1"
        self.assertEqual(F.fix(t), "[Chiip Proviser 2026-11-19]\n\n* Pulse 9.3(+0.1)\n* Analysis 8.3(-0.4)\n* Portfolio 8.7(+0.1)\n\n"
                                   "* Weekly 3.0(+0.0)\n* Model Lab 8.2(+0.0)\n\n18개 7일 평균 8.1")

    def test_no_break_added_when_missing(self):
        t = "* Pulse 9.3(+0.1)\n* Analysis 8.3(-0.4)\n* Portfolio 8.7(+0.1)\n* Weekly 3.0(+0.0)"
        self.assertIn("* Portfolio 8.7(+0.1)\n\n* Weekly", F.fix(t))


if __name__ == "__main__":
    unittest.main()
