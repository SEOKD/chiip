"""Chiip RDIMM Spot — 주간 글 파싱·WoW 역산·그림 판독(2026-11-23 마스터 지시)"""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import rdimm_spot as R  # noqa: E402

POST = {"id": 8887, "at": "2026-11-23T17:52:48+09:00", "url": "https://t.me/Badonions/8887", "image": "u", "image_files": ["a.jpg"],
        "text": "RDIMM Spot Price\n26년 11월 23일\n- DDR5 RDIMM 32GB: $1,645 → WoW -11.80%\n- DDR5 RDIMM 64GB: $2,635 → WoW -7.54%"}


def synth(path, start, end, f32, f64, fc, w=800, h=400):
    """원본과 같은 색·배치의 그림을 만든다(선 두 개 + 계약가 점선)"""
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=w, height=h)
    page.draw_rect(page.rect, color=None, fill=(11 / 255, 19 / 255, 32 / 255))
    x0, y0, x1, y1 = 95, 97, 720, 356
    page.draw_rect((x0, y0, x1, y1), color=None, fill=(15 / 255, 27 / 255, 49 / 255))
    span, k = (end - start).days, 3600 / (y1 - y0)
    xe = x1 - 12
    X = lambda d: x0 + (xe - x0) * d / span          # noqa: E731
    Y = lambda v: y1 - v / k                         # noqa: E731
    for f, col in ((f64, (69 / 255, 204 / 255, 200 / 255)), (f32, (80 / 255, 131 / 255, 222 / 255))):
        page.draw_polyline([pymupdf.Point(X(d), Y(f(d))) for d in range(0, span + 1, 3)], color=col, width=2)
    page.draw_circle(pymupdf.Point(X(span), Y(f32(span))), 3, color=(80 / 255, 131 / 255, 222 / 255), fill=(80 / 255, 131 / 255, 222 / 255))
    c0 = span - 330
    page.draw_polyline([pymupdf.Point(X(d), Y(fc(d))) for d in range(c0, span - 80, 3)], color=(69 / 255, 204 / 255, 200 / 255), width=2, dashes="[4 3] 0")
    page.get_pixmap(dpi=72).save(str(path))


class TestRdimm(unittest.TestCase):
    def test_parse_and_wow_back(self):
        r = R.parse_post(POST)
        self.assertEqual((r["obs_date"], r["gb32"], r["gb64"], r["wow64"]), ("2026-11-23", 1645.0, 2635.0, -7.54))
        ex = R.exact_points([r])
        self.assertEqual(ex[date(2026, 11, 23)][:2], (1645.0, 2635.0))
        self.assertEqual(ex[date(2026, 11, 16)], (1865, 2850, "WoW 역산"))      # 지난주 글의 실제 값과 같다
        self.assertIsNone(R.parse_post({"id": 1, "text": "Memory Price Weekly Update — DRAM"}))
        old = R.parse_post({"id": 2, "text": "RDIMM Spot Price\n26년 11월 2일", "url": "u"})
        self.assertEqual((old["obs_date"], old["gb32"]), ("2026-11-02", ""))     # 숫자 없는 옛 글은 날짜·그림만

    def test_trendforce_module_row(self):
        """원 출처 — TrendForce 공개 '모듈 현물가' 표의 32GB RDIMM 행(2026-11-23 마스터 지시 "원 출처를 찾아라")"""
        page = ("<li>Module Spot Price</li><li>GDDR Spot Price</li><h3>Module Spot Price</h3><span>Last Update 2026-11-16 14:40 (GMT+8)</span>"
                "<table><tr><td>DDR5 UDIMM 16GB 4800/5600</td><td>283.00</td><td>227.00</td><td>283.00</td><td>227.00</td><td>244.333</td><td>▼</td><td>-0.27 %</td></tr>"
                "<tr><td>DDR5 RDIMM 32GB 4800/5600</td><td>2,000.00</td><td>1,750.00</td><td>2,000.00</td><td>1,750.00</td><td>1,865.00</td><td>▼</td><td>-4.36 %</td></tr>"
                "<tr><td>DDR4 UDIMM 16GB 3200</td><td>183.00</td></tr></table>")
        r = R.parse_module(page)
        self.assertEqual((r["date"], r["high"], r["low"], r["avg"], r["chg"]), ("2026-11-16", 2000.0, 1750.0, 1865.0, -4.36))
        self.assertIsNone(R.parse_module("<h3>DRAM Spot Price</h3>"))

    def test_digitize_synthetic_chart(self):
        start, end = date(2024, 10, 7), date(2026, 11, 23)
        span = (end - start).days
        f32 = lambda d: 120 + 1500 * (d / span) ** 3          # noqa: E731
        f64 = lambda d: 260 + 2400 * (d / span) ** 3          # noqa: E731
        fc = lambda d: 0.5 * f64(d)                           # noqa: E731
        img = Path(tempfile.mkdtemp()) / "c.png"
        synth(img, start, end, f32, f64, fc)
        anchors = {date(2026, 11, 16): (round(f32(span - 7)), round(f64(span - 7))), end: (round(f32(span)), round(f64(span)))}
        out = R.digitize(img, end, anchors, start)
        self.assertLessEqual(out["fit"]["max_abs_resid"], 40)
        mid = out["spot"][80]                                  # 80주차 — 판독값이 참값의 ±$45 안
        d = 80 * 7
        self.assertAlmostEqual(mid[1], f32(d), delta=45)
        self.assertAlmostEqual(mid[2], f64(d), delta=45)
        self.assertGreaterEqual(len(out["contract"]), 6)       # 계약가 점선도 월말 값으로 읽는다
        m, v = out["contract"][3]
        self.assertAlmostEqual(v, fc((date.fromisoformat(m) - start).days), delta=60)


if __name__ == "__main__":
    unittest.main()
