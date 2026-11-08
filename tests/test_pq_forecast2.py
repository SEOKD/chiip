"""P·Q 투영 2차 보완 — 이름 풀이·겹친 표본 HAC·장기 평균 수축·가격 나우캐스트, BOM 음수 글자 위치 (마스터 지시 2026-11-08)"""
import math
import random
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import pq_forecast as F  # noqa: E402
import report_html as rh  # noqa: E402
import sync_view as sv  # noqa: E402


def overlapped(n, mean, seed=1):
    random.seed(seed)
    q = [mean / 4 + random.gauss(0, 0.03) for _ in range(n + 3)]
    return [sum(q[i:i + 4]) for i in range(n)]   # 전년 대비 = 4분기 합(겹친 표본)


class TestPQForecast2(unittest.TestCase):
    def test_ar_name(self):
        self.assertEqual(F.ar_name(2), "자기회귀모델(과거 2개 시점)")

    def test_overlap_widens_sigma(self):
        y = overlapped(40, 0.1)
        a = F.ar_fit(y, intercept=True)
        b = F.ar_fit(y, intercept=True, overlap=4)
        self.assertGreaterEqual(b["sigma"], a["sigma"])

    def test_mean_shrinks_to_prior(self):
        y = overlapped(24, 0.5)   # 고성장 표본
        f = F.ar_fit(y, intercept=True, mean_prior=math.log(1.04), mean_k=24)
        self.assertLess(f["mean"], f["mean_raw"])
        self.assertAlmostEqual(f["mean"], 0.5 * f["mean_raw"] + 0.5 * math.log(1.04), places=6)
        path, _ = F.ar_path(y, f, 40)
        self.assertLess(abs(path[-1] - f["mean"]), abs(path[-1] - f["mean_raw"]))

    def test_nowcast_uses_published_months(self):
        mon = {"2025-10": 100.0, "2025-11": 100.0, "2025-12": 100.0, "2026-10": 105.0, "2026-11": 107.0}
        g, n = F.nowcast_yoy(mon, (2026, 12), sv.months_back)
        self.assertEqual(n, 2)
        self.assertAlmostEqual(g, math.log(212 / 200))
        self.assertEqual(F.nowcast_yoy({"2026-01": 1.0}, (2026, 12), sv.months_back), (None, 0))

    def test_negative_bar_label_right_of_zero(self):
        svg = rh.chart_hbars({"w": 480, "label_w": 150, "unit": "%", "rows": [
            {"label": "엔진·엔진 블록(외부 조달, 공급사 포함)", "bars": [{"name": "원가 몫", "color": "e", "value": 52.5}, {"name": "OPM 변화(%p)", "color": "b", "value": -3.24}]},
            {"label": "발전기", "bars": [{"name": "원가 몫", "color": "e", "value": 20.0}, {"name": "OPM 변화(%p)", "color": "b", "value": -0.31}]}]})
        label_x = float(re.search(r'<tspan x="([\d.]+)"', svg).group(1))
        zero_x = float(re.search(r'<line x1="([\d.]+)"', svg).group(1))
        for x, _ in re.findall(r'<text x="([\d.]+)" y="[\d.]+">(-[\d.]+%)</text>', svg):
            self.assertGreater(float(x), zero_x)
            self.assertGreater(float(x), label_x)


if __name__ == "__main__":
    unittest.main()
