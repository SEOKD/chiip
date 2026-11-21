"""Weekly 섹터 온도 선정 + Pulse GPU 렌털료 월요일 점검(마스터 지시 2026-11-14)"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "weekly"))
sys.path.insert(0, str(ROOT / "radar"))
import gpu_weekly  # noqa: E402
import sector_moves  # noqa: E402

KST = timezone(timedelta(hours=9))


def sec(r5, rs5, chiip=False):
    return {"name": "x", "r5": r5, "rs5": rs5, "r20": 0.0, "chiip": chiip}


class TestSectorPick(unittest.TestCase):
    def test_ai_always_and_relative_movers_both_sides(self):
        data = {"sectors": {"ai": sec(0.01, -0.01, True), "up": sec(0.12, 0.09), "down": sec(-0.06, -0.09),
                            "flat1": sec(0.03, 0.0), "flat2": sec(0.031, 0.001), "flat3": sec(0.029, -0.001), "flat4": sec(0.028, -0.002)}}
        ids = [r["id"] for r in sector_moves.pick(data, {"big": 0.04, "top": 1, "max": 16})]
        self.assertEqual(ids, ["up", "ai", "down"])   # 주간 등락 내림차순, 보합 섹터는 빠진다
        rows = {r["id"]: r for r in sector_moves.pick(data, {"big": 0.04, "top": 1})}
        self.assertEqual(rows["down"]["why_in"], "시장보다 크게 내림")
        self.assertEqual(rows["ai"]["why_in"], "AI 밸류체인")

    def test_broad_rally_does_not_crowd_out_decliners(self):
        data = {"sectors": {**{f"u{i}": sec(0.06, 0.005) for i in range(20)}, "d": sec(-0.05, -0.08)}}
        ids = [r["id"] for r in sector_moves.pick(data, {"big": 0.04, "top": 2})]
        self.assertIn("d", ids)
        self.assertLessEqual(len(ids), 5)   # 시장과 같이 오른 20개는 다 싣지 않는다


ROWS = [{"date": d, "provider": p, "gpu": "H100", "config": c, "term": t, "usd_per_gpu_hr": v}
        for d, p, c, t, v in (("2026-11-10", "Nebius", "", "온디맨드", "4.50"), ("2026-11-17", "Nebius", "", "온디맨드", "4.95"),
                              ("2026-11-10", "Silicon Data 지수", "", "지수", "3.00"), ("2026-11-17", "Silicon Data 지수", "", "지수", "3.00"),
                              ("2026-11-10", "Lambda", "HGX H100 8x", "온디맨드", "3.99"),
                              ("2026-11-10", "Lambda", "HGX H100 8x", "온디맨드(시행 November 16, 2026)", "4.59"))]


class TestGpuWeekly(unittest.TestCase):
    def test_weekly_change_and_lambda_effective_date(self):
        t = gpu_weekly.table("2026-11-17", ROWS)
        r = t["rows"][0]
        self.assertAlmostEqual(r["Nebius"]["wk"], 10.0)
        self.assertEqual(set(k for k in r if k != "gpu"), {"Nebius", "CoreWeave", "AWS"})   # 세 곳 온디맨드만(2026-11-16 마스터 지시)
        msg = gpu_weekly.message(t, "풀이")
        self.assertIn("■움직인 지표\nH100 Nebius +10.0%", msg)
        self.assertIn("■H100: Nebius $4.95(+10.0%)", msg)   # 한 곳뿐이면 머리 줄에
        for gone in ("지수", "Lambda", "스팟"):
            self.assertNotIn(gone, msg)

    def test_index_reference_line_not_in_movers(self):
        rows = [{"date": d, "provider": "Silicon Data 지수", "gpu": "H100", "config": "H100 지수", "term": "시장 지수(인용)", "usd_per_gpu_hr": v}
                for d, v in (("2026-11-16", "3.00"), ("2026-11-23", "2.90"), ("2026-11-23", "3.09"))]
        rows += [{"date": d, "provider": "Nebius", "gpu": "H100", "config": "NVIDIA HGX H100", "term": "온디맨드", "usd_per_gpu_hr": "4.50"}
                 for d in ("2026-11-16", "2026-11-23")]
        t = gpu_weekly.table("2026-11-23", rows)
        self.assertEqual(t["moved"], [])                                   # 세 곳 정가만 '움직인 지표'
        self.assertEqual(t["index"], [("H100", 3.09, t["index"][0][2])])   # 그날 마지막 값
        self.assertAlmostEqual(t["index"][0][2], 3.0, places=1)
        self.assertIn("참고 시장 지수(Silicon Data) H100 $3.09(+3.0%)", gpu_weekly.message(t, ""))

    def test_due_only_monday_after_six_once_per_week(self):
        with mock.patch.object(gpu_weekly.common, "load_state", return_value={}), mock.patch.object(gpu_weekly, "table", return_value={"rows": [1], "moved": [], "as_of": "2026-11-16", "prev": "2026-11-09"}), \
                mock.patch.object(gpu_weekly, "message", return_value=""):
            self.assertFalse(gpu_weekly.status(datetime(2026, 11, 16, 5, 50, tzinfo=KST))["due"])
            self.assertTrue(gpu_weekly.status(datetime(2026, 11, 16, 6, 0, tzinfo=KST))["due"])
            self.assertFalse(gpu_weekly.status(datetime(2026, 11, 17, 6, 0, tzinfo=KST))["due"])
        with mock.patch.object(gpu_weekly.common, "load_state", return_value={"done": "2026-W47"}):
            self.assertFalse(gpu_weekly.status(datetime(2026, 11, 16, 9, 0, tzinfo=KST))["due"])


class TestThemeGate(unittest.TestCase):
    def test_renderer_rejects_theme_outside_taxonomy(self):
        import render
        c = render.cfg()
        self.assertIn("클라우드·데이터센터", c["themes"])
        self.assertNotIn("사이버보안·SW", c["themes"])
        rows = "region,rank,pct_change,name_ko,desc_ko,theme,ticker\nUS,1,10,코어위브,GPU 클라우드,사이버보안·SW,CRWV\n"
        cc = {**c, "regions": [{"key": "US", "title": "US", "count": 1}]}
        with mock.patch.object(Path, "read_text", return_value=rows):
            with self.assertRaises(ValueError):
                render.load_movers("2026-W46", cc)
        with mock.patch.object(Path, "read_text", return_value=rows.replace("사이버보안·SW", "클라우드·데이터센터")):
            self.assertEqual(render.load_movers("2026-W46", cc)[0]["rows"][0]["theme"], "클라우드·데이터센터")


if __name__ == "__main__":
    unittest.main()
