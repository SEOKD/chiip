"""SVG 안 글자 색칠·사진 한 줄(2026-11-13 LTH 어닝콜·몬테카를로 그림 깨짐)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import report_html as rh  # noqa: E402


class TestSvgSafe(unittest.TestCase):
    def test_signed_percent_labels_stay_svg(self):
        s = rh.CHARTS["hbars"]({"w": 480, "label_w": 150, "unit": "%", "rows": [{"label": "월 회비 +12%", "bars": [{"name": "v", "value": -2.1}]}, {"label": "회원 −0.1%", "bars": [{"name": "v", "value": 0.9}]}]})
        svg = s[s.index("<svg"):]
        self.assertNotIn("<span", svg)
        self.assertIn("<tspan style=\"fill:var(--b)", svg)
        self.assertIn("<tspan style=\"fill:var(--c)", svg)

    def test_bars_categories_with_signs(self):
        s = rh.CHARTS["bars"]({"unit": "%", "categories": ["-100%", "+20%"], "series": [{"name": "빈도", "values": [1, 2]}]})
        self.assertNotIn("<span", s[s.index("<svg"):])

    def test_photo_strip_is_one_row(self):
        self.assertIn(".phs{display:flex", rh.CSS if hasattr(rh, "CSS") else Path(rh.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
