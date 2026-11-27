"""재고 일수 그림 — 보강 선(재고−매출 증가율 갭·매출총이익률)과 한눈에 보기 위치(마스터 지시 2026-11-27)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import ops_view  # noqa: E402


class TestInventory(unittest.TestCase):
    def test_reading_lines(self):
        rows = [{"period": f"2026-0{i}-30", "bb": None, "bb4": None, "dio": 30 + i, "inv_yoy": 0.3, "rev_yoy": 0.1, "gpm": 0.40 - i * 0.01} for i in range(1, 5)]
        saved = ops_view.cycle
        ops_view.cycle = lambda dp: rows
        try:
            sec = ops_view.cycle_section({})
        finally:
            ops_view.cycle = saved
        ch = [b for b in sec["blocks"] if b["type"] == "chart"][0]["chart"]
        self.assertTrue(ch["multi_axis"])
        self.assertEqual([s["axis"] for s in ch["series"]], ["dio", "gap", "gpm"])
        self.assertIn("안 팔린 재고 경고", ch["title"])

    def test_gallery_position_code(self):
        src = (ROOT / "scripts" / "tenbagger" / "report_layout.py").read_text(encoding="utf-8")
        self.assertIn('startswith("BOM 항목 가격")', src)
        self.assertIn('startswith("재고 일수")', src)


if __name__ == "__main__":
    unittest.main()
