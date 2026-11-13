"""추정치 수정 폭(마스터 선택 2026-11-14)"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import breadth as br  # noqa: E402

T = date(2026, 11, 13)
ROWS = [
    ["analyst_eps", "A", "2026-12-31", "2026-08-01", 1.70, 4],   # 창 앞 기준값
    ["analyst_eps", "A", "2026-12-31", "2026-10-20", 1.75, 4],   # 상향
    ["analyst_eps", "Q", "2026-12-31", "2026-10-01", 0.40, 4],
    ["analyst_eps", "Q", "2026-12-31", "2026-10-20", 0.41, 4],   # 같은 날 분기도 상향 → 하루 1건
    ["analyst_eps", "A", "2026-12-31", "2026-10-25", 1.80, 5],   # 애널리스트 수 변화 → 커버리지
    ["analyst_eps", "A", "2026-12-31", "2026-11-01", 1.79, 5],   # 하향
    ["analyst_eps", "A", "2026-12-31", "2026-11-05", 1.7901, 5], # 0.1% 미만 — 무시
    ["analyst_eps", "A", "2026-12-31", "2026-11-06", 1.85, 5],   # 상향
    ["analyst_eps", "A", "2025-12-31", "2026-11-06", 9.99, 5],   # 끝난 기간 — 무시
]


class TestBreadth(unittest.TestCase):
    def test_events_one_per_day_and_cov(self):
        ev = br.events(ROWS, T, 0.001)
        self.assertEqual([(e[0].isoformat(), e[2]) for e in ev],
                         [("2026-10-20", "up"), ("2026-10-25", "cov"), ("2026-11-01", "down"), ("2026-11-06", "up")])

    def test_ratio_and_min_events(self):
        c = {**br.cfg(), "windows": [30, 90], "min_events": 3}
        r = br.compute(ROWS, T, c)
        self.assertEqual((r[30]["EPS"]["up"], r[30]["EPS"]["down"], r[30]["EPS"]["cov"]), (2, 1, 1))
        self.assertAlmostEqual(r[30]["EPS"]["b"], 1 / 3)
        self.assertIsNone(r[30]["매출"]["b"])

    def test_blocks_text_and_empty(self):
        B = br.blocks({"consensus": {"revision_breadth": {"as_of": "2026-11-13", "rows": ROWS}}})
        self.assertIn("상향 2건·하향 1건", B[0]["text"])
        self.assertEqual(B[1]["rows"][0][0], "EPS")
        self.assertEqual(br.blocks({"consensus": {}}), [])

    def test_verdict(self):
        self.assertEqual(br.verdict(0.6, 0.5), "상향 우세")
        self.assertEqual(br.verdict(-0.5, 0.5), "하향 우세")
        self.assertEqual(br.verdict(None, 0.5), "표본 적음")


if __name__ == "__main__":
    unittest.main()
