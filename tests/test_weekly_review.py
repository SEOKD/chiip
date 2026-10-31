import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "weekly"))
sys.path.insert(0, str(ROOT / "radar"))
import render  # noqa: E402


def doc():
    return json.loads((ROOT / "outputs" / "brief" / "2026-W44_weekly.json").read_text(encoding="utf-8"))


class TestWeeklyReview(unittest.TestCase):
    def setUp(self):
        self.c = render.cfg()

    def test_gate_passes_good_report(self):
        render.check(doc(), self.c)
        movers = render.load_movers("2026-W44", self.c)
        render.lint(render.to_md(doc(), movers), self.c)
        self.assertEqual([r["title"] for r in movers][-2:], ["Taiwan", "Hong Kong"])
        self.assertIn("+33%｜글라우코스｜녹내장 스텐트", render.ticker_block(doc(), movers))
        self.assertEqual(render.themes(movers)[1], 80)

    def test_gate_rejects(self):
        d = doc()
        d["changes"] = d["changes"][:1]
        with self.assertRaises(ValueError):
            render.check(d, self.c)
        d = doc()
        d["headline"] = "가" * 80
        with self.assertRaises(ValueError):
            render.check(d, self.c)
        for bad in ("매출은 미확인이다", "원천 보류로 비었다", "台光電 매출", "knowledge/x.csv 없음", "D-20261030-01"):
            with self.assertRaises(ValueError):
                render.lint(bad, self.c)

    def test_tw_hk_names(self):
        import notify
        self.assertEqual(notify.tw_hk_names("台光電·廣達"), "엘리트머티리얼즈·콴타")


class TestFeedCodes(unittest.TestCase):
    def test_code_gloss(self):
        import notify
        t = notify.brand("사유: T2 실적이면 P1이나 2차 재인용. T2 다시")
        self.assertIn("T2(글로벌 밸류체인 기업)", t)
        self.assertIn("P1(즉시 알림 등급)이나", t)
        self.assertEqual(t.count("T2("), 1)
        self.assertEqual(notify.code_gloss("S-1 T2(이미)"), "S-1 T2(이미)")

    def test_line_chart_keeps_time_order(self):
        sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
        import report_html
        c = {"kind": "line", "title": "t", "unit": "$", "series": [{"name": "a", "color": "a", "points": [["9/4", 1], ["10/2", 2], ["10/30", 3]]}]}
        svg = report_html.chart_line(c)
        self.assertLess(svg.index("9/4"), svg.index("10/30"))


if __name__ == "__main__":
    unittest.main()
