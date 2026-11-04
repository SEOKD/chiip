"""예약 작업 누락 재실행 판정 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ops"))
import catchup as c  # noqa: E402


def task(tid, cron, runs, **kw):
    return {"taskId": tid, "cronExpression": cron, "enabled": True, "jitterSeconds": 300, "runs": runs, **kw}


class TestCatchup(unittest.TestCase):
    NOW = "2026-11-04T23:30:00+09:00"

    def test_missed_slot(self):
        # 22:00 회차 기록 없음 → 재실행
        doc = {"now": self.NOW, "tasks": [task("a", "0 6,9,13,18,22 * * *", [{"started_at": "2026-11-04T09:05:00Z", "status": "succeeded"}])]}
        r = c.judge(doc, {})
        self.assertEqual([x["taskId"] for x in r["rerun"]], ["a"])
        self.assertTrue(r["rerun"][0]["slot"].startswith("2026-11-04T22:00"))

    def test_ok_failed_waiting(self):
        ok = task("ok", "0 22 * * *", [{"started_at": "2026-11-04T13:04:00Z", "status": "succeeded"}])
        bad = task("bad", "0 22 * * *", [{"started_at": "2026-11-04T13:04:00Z", "status": "failed"}])
        run = task("run", "0 22 * * *", [{"started_at": "2026-11-04T13:04:00Z", "status": "running"}])
        r = c.judge({"now": self.NOW, "tasks": [ok, bad, run]}, {})
        self.assertEqual(r["ok"], 1)
        self.assertEqual([x["taskId"] for x in r["rerun"]], ["bad"])
        self.assertEqual(r["waiting"], ["run"])

    def test_no_double_rerun_and_skips(self):
        t = task("a", "0 22 * * *", [])
        self.assertEqual(c.judge({"now": self.NOW, "tasks": [t]}, {"a": {"slot": "2026-11-04T22:00:00+09:00"}})["rerun"], [])
        off = task("off", "0 22 * * *", [], enabled=False)
        once = task("once", "0 14 4 11 *", [])
        selfj = task("chiip-catchup", "50 * * * *", [])
        r = c.judge({"now": self.NOW, "tasks": [off, once, selfj]}, {})
        self.assertEqual(r["rerun"], [])

    def test_frequent_and_weekday(self):
        # 10분 펄스: 직전 회차 하나만 본다 / 주중 전용 작업은 토요일에 회차가 없다
        p = task("p", "*/10 * * * 1-5", [{"started_at": "2026-11-04T14:00:00Z", "status": "succeeded"}])   # 23:00 KST
        self.assertEqual(c.judge({"now": self.NOW, "tasks": [p]}, {})["ok"], 1)
        slot = c.last_slot("0 9 * * 1-5", c._dt("2026-11-07T12:00:00+09:00"))   # 토요일 → 금요일 09:00
        self.assertEqual(slot.isoformat()[:16], "2026-11-06T09:00")


if __name__ == "__main__":
    unittest.main()
