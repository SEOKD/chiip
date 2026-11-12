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

    def test_send_gate(self):   # 회차당 1건·상세 해석(2026-11-12 마스터 지시)
        rows = [row("n1", "Micron_Upgrade_to_OW.pdf", "co-micron")]
        ok = [{"id": "n1", "why": "등급 상향", "conclusion": "c", "claims": ["a", "b", "c"], "numbers": ["1", "2"],
               "logic": "l", "gap": "g", "weak": "w", "next": "n"}]
        self.assertEqual(F.check(ok, rows), [])
        self.assertTrue(F.check(ok * 2, rows))                                     # 2건 이상 거절
        self.assertTrue(F.check([{**ok[0], "claims": ["a", "b"]}], rows))           # 주장 3개 미만
        self.assertTrue(F.check([{**ok[0], "weak": ""}], rows))                     # 약한 고리 없음
        self.assertTrue(F.check([{**ok[0], "logic": "매수하라"}], rows))
        msg = F.message(ok, rows=rows)
        for k in ("[Chiip IB Digest]", "핵심 주장", "근거 숫자", "약한 고리", "다음 확인", "투자 권유가 아님"):
            self.assertIn(k, msg)

    def test_same_report_twice_is_one(self):   # 같은 PDF를 두 번 올려 id가 둘(11/12 Top of Mind)
        rows = [row("a", "Top of Mind_ Is the AI cycle durable_.pdf"), row("b", "Top of Mind_ Is the AI cycle durable_.pdf")]
        c, _ = F.candidates(rows, {"baseline": [], "done": []}, CFG)
        self.assertEqual(len(c), 1)
        c, _ = F.candidates(rows, {"baseline": [], "done": ["a"], "sent_keys": [F.report_key(rows[0]["name"])]}, CFG)
        self.assertEqual(c, [])

if __name__ == "__main__":
    unittest.main()
