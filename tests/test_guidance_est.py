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
        self.assertIn("- GPM 30.7%", out)   # 실적 절은 건드리지 않는다
        self.assertIn("- GPM 32% (est. 31%)", out)
        self.assertEqual(out[-1], "장후 -6.1%")


if __name__ == "__main__":
    unittest.main()
