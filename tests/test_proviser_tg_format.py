"""Proviser 텔레그램 — 점수 목록은 빈 줄 없이, 본문 문단은 ■로 시작(마스터 지시 2026-11-19 예시 양식)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "proviser"))
import tg_format as F  # noqa: E402


class TgFormat(unittest.TestCase):
    def test_example(self):
        t = ("[Chiip Proviser 2026-11-19]\n\n* Pulse 9.3(+0.0)\n* Analysis 8.4(+0.1)\n* Portfolio 8.7(+0.0)\n\n* Weekly 3.0(+0.0)\n* Flow 7.4(-0.4)\n\n"
             "18개 7일 평균 8.1(전주 대비 +0.0)\n\n\n하락 원인: Flow는 …\n\n■이미 붙은 문단")
        self.assertEqual(F.fix(t), "[Chiip Proviser 2026-11-19]\n\n* Pulse 9.3(+0.0)\n* Analysis 8.4(+0.1)\n* Portfolio 8.7(+0.0)\n* Weekly 3.0(+0.0)\n"
                                   "* Flow 7.4(-0.4)\n\n■18개 7일 평균 8.1(전주 대비 +0.0)\n\n■하락 원인: Flow는 …\n\n■이미 붙은 문단")


if __name__ == "__main__":
    unittest.main()
