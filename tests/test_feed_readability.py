"""텔레그램 피드 가독성 채점 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "proviser"))
import feed_readability as fr  # noqa: E402


class TestFeedRead(unittest.TestCase):
    def test_clean_beats_wall(self):
        good = "MU 3Q 매출 $9.3B, 가이던스 상회\n\n- HBM 비중 40%\n- 다음 확인: 12/17 실적\n\n출처: https://x.com/a"
        wall = "\n".join(["P1 T0 소식 미확인 미확인 미확인 " + "가" * 120 + " 1 2 3 4 5 6 7 8 9"] * 10)
        gs, _ = fr.score(good)
        ws, m = fr.score(wall)
        self.assertGreater(gs, 9)
        self.assertLess(ws, 4)
        self.assertGreater(m["내부 코드"], 0)

    def test_run_by_function(self):
        rows = [{"at": "x", "level": "PULSE", "text": "짧은 결론 3%\n\n본문"}, {"at": "y", "level": "PORTFOLIO", "text": "가" * 200}]
        _, out = fr.run("20261104", 1, rows=rows)
        self.assertEqual(set(out), {"Pulse", "Portfolio"})
        self.assertIn(out["Portfolio"]["weakest"], out["Portfolio"]["penalty"])


if __name__ == "__main__":
    unittest.main()
