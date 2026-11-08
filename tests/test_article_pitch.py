"""기사 소재 — 채택 버튼·후보 풀·프로바이저 채택률 (2026-11-08 점검·보완)"""
import csv
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "article"))
sys.path.insert(0, str(ROOT / "scripts" / "proviser"))
import pitch_feedback as F  # noqa: E402
import pitch_pool as PP  # noqa: E402


class TestFeedback(unittest.TestCase):
    def setUp(self):
        self.log = Path(tempfile.mkdtemp()) / "log.csv"
        with self.log.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "pitch_id", "yama", "sources", "adopted"])
            w.writerow(["2026-11-09", "PITCH-20261109-01", "a", "s", ""])
            w.writerow(["2026-11-09", "PITCH-20261109-02", "b", "s", ""])

    def rows(self):
        with self.log.open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def test_buttons_follow_pitch_count(self):
        text = "[기사 소재 11/09] 2건\n\n기사①\n■ a\n\n기사②\n■ b"
        b = F.buttons("20261109", F.count(text))
        self.assertEqual([t for t, _ in b[0]], ["① 채택", "② 채택"])
        self.assertEqual(b[1][0][1], "pitch:20261109:0:n")

    def test_callback_marks_one_and_pass_all(self):
        note, markup = F.on_callback("pitch:20261109:2:y", self.log)
        self.assertIn("②", note)
        r = self.rows()
        self.assertEqual(r[0]["adopted"], "")
        self.assertTrue(r[1]["adopted"].startswith("채택"))
        F.on_callback("pitch:20261109:0:n", self.log)
        self.assertEqual({x["adopted"] for x in self.rows()}, {"패스"})


class TestKpi(unittest.TestCase):
    def test_blank_is_not_zero(self):
        import quality
        orig = quality._rows
        quality._rows = lambda p: [{"date": "2026-11-08", "adopted": ""}, {"date": "2026-11-08", "adopted": ""}]
        try:
            self.assertEqual(quality.pitch_adoption_30d(date(2026, 11, 9)), (None, 0))
            quality._rows = lambda p: [{"date": "2026-11-08", "adopted": "채택 2026-11-08 07:00"}, {"date": "2026-11-08", "adopted": "패스"}, {"date": "2026-11-08", "adopted": ""}]
            self.assertEqual(quality.pitch_adoption_30d(date(2026, 11, 9)), (0.5, 2))
        finally:
            quality._rows = orig


class TestPool(unittest.TestCase):
    def test_korea_link_and_penalties(self):
        info = {"co-skhynix": ("SK하이닉스", True), "co-micron": ("Micron", False), "eu-x": ("X사", False)}
        ind_of, korea_ind = {"co-micron": ["dram-hbm"]}, {"dram-hbm": True}
        self.assertEqual(PP.korea_link(["co-skhynix"], info, ind_of, korea_ind)[0], 2)
        self.assertEqual(PP.korea_link(["co-micron"], info, ind_of, korea_ind)[0], 1)
        self.assertEqual(PP.korea_link(["eu-x"], info, ind_of, korea_ind)[0], 0)
        orig_p, orig_d = PP.recent_pitched, PP.recent_dticker
        PP.recent_pitched, PP.recent_dticker = (lambda today, days=7: "Micron 재고"), (lambda days=7: "")
        try:
            out = PP.score([{"ids": ["co-micron"], "event": "매출 +20%", "primary": True, "insight": 6},
                            {"ids": ["co-skhynix"], "event": "HBM 단가", "primary": True, "insight": 6}], (None, info, ind_of, korea_ind), date(2026, 11, 9))
        finally:
            PP.recent_pitched, PP.recent_dticker = orig_p, orig_d
        self.assertEqual(out[0]["names"], ["SK하이닉스"])
        self.assertIn("최근 7일 기사 소재로 냄", out[1]["notes"])


if __name__ == "__main__":
    unittest.main()
