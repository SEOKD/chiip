"""Proviser 대상 — 켜진 반복 예약 작업 전부, 새 기능 자동 편입(마스터 지시 2026-11-09)"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "proviser"))
import targets as T  # noqa: E402


class TestTargets(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "config").mkdir()
        (self.tmp / "docs" / "proviser").mkdir(parents=True)
        shutil.copy(ROOT / "config" / "proviser_targets.yaml", self.tmp / "config")
        self.old = (T.ROOT, T.REG)
        T.ROOT, T.REG = self.tmp, self.tmp / "config" / "proviser_targets.yaml"

    def tearDown(self):
        T.ROOT, T.REG = self.old
        shutil.rmtree(self.tmp)

    def test_all_recurring_enabled_and_new_feature(self):
        tasks = [{"taskId": "chiip-pulse", "title": "Chiip Pulse", "cronExpression": "*/10 * * * 1-5", "enabled": True},
                 {"taskId": "chiip-proviser", "title": "Chiip Proviser", "cronExpression": "0 23 * * *", "enabled": True},
                 {"taskId": "once", "title": "1회", "fireAt": "2026-11-08T10:20:00Z", "enabled": True},
                 {"taskId": "chiip-future-x", "title": "Chiip Future X", "description": "지시문 원본 docs/tasks/chiip-future-x.md", "cronExpression": "0 9 * * *", "enabled": True}]
        out, new, gone = T.run(tasks, "2026-11-09")
        ids = [x["taskId"] for x in out]
        self.assertEqual(ids, ["chiip-pulse", "chiip-future-x"])            # 자신·1회성 제외
        self.assertEqual(new, ["chiip-future-x"])
        self.assertTrue((self.tmp / "docs" / "proviser" / "chiip-future-x.md").exists())
        self.assertIn("docs/tasks/chiip-future-x.md", (self.tmp / "docs" / "proviser" / "chiip-future-x.md").read_text(encoding="utf-8"))
        self.assertIn("chiip-future-x", T.REG.read_text(encoding="utf-8"))
        self.assertIn("chiip-industry-weekly", gone)                           # 목록에 없는 기존 대상은 '꺼짐·삭제'로 알린다
        out2, new2, _ = T.run(tasks, "2026-11-10")
        self.assertEqual(new2, [])                                             # 두 번째부터는 새로 들어온 것이 아니다


if __name__ == "__main__":
    unittest.main()
