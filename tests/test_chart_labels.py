"""그래프 x축 이름표 겹침 방지 (마스터 지시 2026-11-08 — 매출 → 매출총이익 → 영업이익 그림)"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import report_html as R  # noqa: E402

LONG = ["매출", "소재(동박적층판·구리·금·화학약품)", "인건비·공장 간접비(중국·말레이시아·미국)", "기타 매출원가(수율·외주·물류)", "감가상각", "기타 매출원가",
        "매출총이익", "연구개발", "판관비", "감가상각", "기타 영업비용", "영업이익"]


class TestLabels(unittest.TestCase):
    def test_each_line_fits_slot(self):
        for txt in LONG:
            for line in R.wrap_label(txt, 46):
                self.assertLessEqual(sum(R._label_w(ch, 9.5) for ch in line), 46 + 0.01, line)

    def test_waterfall_labels_do_not_overlap(self):
        steps = [{"label": x, "kind": "total" if x in ("매출", "매출총이익", "영업이익") else "cost", "value": 100 if x == "매출" else -3} for x in LONG]
        svg = R.chart_waterfall({"steps": steps})
        W = 700
        gw = (W - 40 - 10) / len(steps)
        for m in re.finditer(r"<tspan x=\"([\d.]+)\"[^>]*>([^<]*)</tspan>", svg):
            w = sum(R._label_w(ch, 9.5) for ch in m.group(2))
            self.assertLessEqual(w, gw - 4 + 0.01)   # 한 줄 폭 ≤ 칸 폭 → 이웃 이름표와 겹치지 않는다

    def test_full_text_kept_in_title(self):
        self.assertIn("<title>인건비·공장 간접비(중국·말레이시아·미국)</title>", R.label_svg(LONG[2], 100, 200, 46)[0])


if __name__ == "__main__":
    unittest.main()
