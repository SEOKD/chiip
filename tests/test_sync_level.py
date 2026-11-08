"""매출·PPI·수출입 같은 축 그림 (마스터 지시 2026-11-08 — 최근 16개 분기, 매출과 지표 시계열 동일)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import sync_view as sv  # noqa: E402


class TestLevel(unittest.TestCase):
    def test_window_is_16_quarters(self):
        w = sv.window("2026Q3")
        self.assertEqual((len(w), w[0], w[-1]), (16, "2022Q4", "2026Q3"))

    def test_same_axis_and_base(self):
        rev = {q: 100 + i for i, q in enumerate(sv.window("2026Q3")[6:])}     # 매출은 10개 분기뿐(분리 뒤 재작성처럼)
        ind = {q: 50 + i for i, q in enumerate(sv.window("2026Q3"))}           # 지표는 16개 분기
        c = {"rev": rev, "rows": [{"ind": {"label": "EU 저장장치 수입", "source": "hs"}, "iq": ind}]}
        ch = sv.level_chart(c, sv.window("2026Q3"))
        first = min(rev)
        self.assertIn(f"{first} = 100", ch["title"])
        for s in ch["series"]:
            self.assertEqual(s["points"][0], [first, 100.0])                   # 모든 시계열이 같은 기준 분기
            self.assertTrue(all(p[0] in rev for p in s["points"]))            # 매출이 없는 분기는 지표도 그리지 않는다

    def test_indicator_gap_trims_all_series(self):
        w = sv.window("2026Q3")
        rev = {q: 100 + i for i, q in enumerate(w)}
        ind = {q: 50 + i for i, q in enumerate(w) if q not in ("2023Q3", "2023Q4")}   # 지표가 빈 분기는 매출도 그리지 않는다
        ch = sv.level_chart({"rev": rev, "rows": [{"ind": {"label": "한국 변압기 PPI", "source": "ppi"}, "iq": ind}]}, w)
        qs = [[p[0] for p in s["points"]] for s in ch["series"]]
        self.assertEqual(qs[0], qs[1])
        self.assertNotIn("2023Q3", qs[0])


if __name__ == "__main__":
    unittest.main()
