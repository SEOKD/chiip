"""Chiip IB Digest — 새 IB PDF 감지·1차 점수·발송 관문 (마스터 지시 2026-11-08)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import ib_digest_feed as F  # noqa: E402

CFG = {"themes": [{"match": ["Utilities"], "subs": ["Electric Utilities"]}]}


def row(i, name, ent=""):
    return {"id": i, "name": name, "cls": "IB 리포트", "entities": ent, "status": "text", "chars": "50000", "broker": "JPM", "doc_date": "2026-11-08"}


class TestFeed(unittest.TestCase):
    def test_first_run_is_baseline(self):
        c, st = F.candidates([row("a", "x.pdf")], {}, CFG)
        self.assertEqual(c, [])
        self.assertEqual(st["baseline"], ["a"])

    def test_new_files_scored(self):
        rows = [row("old", "x.pdf"), row("n1", "Micron_Upgrade_to_OW.pdf", "co-micron"), row("n2", "Americas_Utilities_weekly.pdf"), row("n3", "Crocs_review.pdf")]
        c, _ = F.candidates(rows, {"baseline": ["old"], "done": []}, CFG)
        self.assertEqual([x["id"] for x in c], ["n1", "n2", "n3"])   # 주 대상+등급 변경 > 업종 테마 > 감시 밖

    def test_send_gate(self):
        ok = [{"id": "n1", "why": "등급 상향", "points": ["a", "b"], "chiip": "같다"}]
        self.assertEqual(F.check(ok), [])
        self.assertTrue(F.check(ok * 4))
        self.assertTrue(F.check([{"id": "n1", "why": "w", "points": ["매수하라", "b"]}]))
        msg = F.message(ok, rows=[row("n1", "Micron_Upgrade_to_OW.pdf", "co-micron")])
        self.assertIn("[Chiip IB Digest]", msg)
        self.assertIn("투자 권유가 아님", msg)


if __name__ == "__main__":
    unittest.main()
