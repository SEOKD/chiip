"""알파 감지 알림 — 기업 1줄·가정 줄 마지막·깨진 내러티브 머리 (마스터 지시 2026-11-08)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "valuation" / "v2"))
import alpha_watch as aw  # noqa: E402

R = {"entity": "co-ies", "drivers_as_of": "2026-11-08", "market": {"date": "2026-11-08"}, "coc": {"wacc": 0.101},
     "upside": {"implied_cagr": None, "n": 3000}}


class TestAlphaMessage(unittest.TestCase):
    def test_company_line_after_reasons_and_assumption_last(self):
        L = aw.message(R, "IES Holdings", 6.4, ["알파 5.3 기준 진입"], update_note="갱신").split("\n")
        # 2026-11-11 마스터 지시: 근거는 풀어 쓰고, 마지막 '가정:' 줄은 뺀다
        self.assertTrue(L[1].startswith("☞"))
        self.assertIn("왜 감지됐나", L)
        self.assertNotIn("**", L)
        self.assertNotIn("투자자문 아님", L)
        self.assertIn("기준(5.0)을 처음 넘었다", "\n".join(L))
        self.assertFalse(any(x.startswith("가정:") for x in L))
        self.assertNotIn("보수 가정", "\n".join(L))

    def test_broken_front_still_reads(self):
        text = "---\nid: co-x\nas_of: 2026-11-08\nsummary: 'A + B'가 1순위 — 설명\nstage: 확산\nalpha_effect: {gap: +1, upside: 0}\n---\n본문"
        self.assertIsNotNone(aw.check_front(text))
        fm = aw.front(text)
        self.assertEqual(fm["stage"], "확산")
        self.assertIn("1순위", fm["summary"])
        self.assertEqual(fm["alpha_effect"]["gap"], 1)

    def test_good_front_passes_check(self):
        self.assertIsNone(aw.check_front('---\nid: co-x\nsummary: "‘A’가 1순위"\n---\n'))


if __name__ == "__main__":
    unittest.main()
