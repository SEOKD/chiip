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
        self.assertEqual(r["지수"]["wk"], 0.0)
        self.assertEqual(r["Lambda"]["now"], 4.59)        # 11-16 시행가
        self.assertAlmostEqual(r["Lambda"]["wk"], (4.59 / 3.99 - 1) * 100)
        self.assertEqual(gpu_weekly.table("2026-11-14", ROWS)["rows"][0]["Lambda"]["now"], 3.99)   # 시행 전에는 옛 가격
        msg = gpu_weekly.message(t, "풀이")
        self.assertIn("H100 Nebius +10.0%", msg)

    def test_due_only_monday_after_six_once_per_week(self):
        with mock.patch.object(gpu_weekly.common, "load_state", return_value={}), mock.patch.object(gpu_weekly, "table", return_value={"rows": [1], "moved": [], "as_of": "2026-11-16", "prev": "2026-11-09"}), \
                mock.patch.object(gpu_weekly, "message", return_value=""):
            self.assertFalse(gpu_weekly.status(datetime(2026, 11, 16, 5, 50, tzinfo=KST))["due"])
            self.assertTrue(gpu_weekly.status(datetime(2026, 11, 16, 6, 0, tzinfo=KST))["due"])
            self.assertFalse(gpu_weekly.status(datetime(2026, 11, 17, 6, 0, tzinfo=KST))["due"])
        with mock.patch.object(gpu_weekly.common, "load_state", return_value={"done": "2026-W47"}):
            self.assertFalse(gpu_weekly.status(datetime(2026, 11, 16, 9, 0, tzinfo=KST))["due"])


if __name__ == "__main__":
    unittest.main()
