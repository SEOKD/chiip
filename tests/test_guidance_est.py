"""실적 피드 Guidance 줄 est. 관문(마스터 지시 2026-11-11)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import notify  # noqa: E402

T = "[실적] X\n4Q Results\n- 매출 $39.3M (est. $40.3M)\n- GPM 30.7%\n\nFY27 Guidance\n- 매출 $195M~$205M\n- GPM 32% (est. 31%)\n\n장후 -6.1%"


class T1(unittest.TestCase):
    def test_marks_missing_only_in_guidance(self):
        out = notify.guidance_est(T).split("\n")
        self.assertIn("- 매출 $195M~$205M (est. 없음)", out)
        self.assertIn("- GPM 30.7% (est. 없음)", out)   # 2026-11-20부터 실적 절 핵심 지표 줄도 관문 대상
        self.assertIn("- GPM 32% (est. 31%)", out)
        self.assertEqual(out[-1], "장후 -6.1%")


class T2(unittest.TestCase):
    def test_cash_lines_in_results(self):   # 2026-11-19 ROAD FY26
        x = "FY26 Results\n- 매출 $3.674B (est. $3.659B)\n- OCF $344.0M\n- CAPEX $182.1M (est. $195.0M)\n- FCF $161.8M\n\n장전 +1.3%"
        out = notify.guidance_est(x).split("\n")
        self.assertIn("- OCF $344.0M (est. 없음)", out)
        self.assertIn("- CAPEX $182.1M (est. $195.0M)", out)
        self.assertIn("- FCF $161.8M (est. 없음)", out)


class T3(unittest.TestCase):
    def test_header_tail_and_blank_line(self):   # 2026-11-20 ESE — 머리 꼬리·머리 아래 빈 줄
        x = "FY27 Guidance (Megger 편입)\n\n- Megger 매출 $640M~$660M\n- EBITDA 마진 24.2~24.8%\n\n장전 +1.3%"
        out = notify.guidance_est(x).split("\n")
        self.assertIn("- EBITDA 마진 24.2~24.8% (est. 없음)", out)
        self.assertEqual(out[-1], "장전 +1.3%")


if __name__ == "__main__":
    unittest.main()
