"""예측 원장 채점(2026-11-24 점검 D4) — 칸이 밀린 행·판정값 형식을 잡고, 같은 주체의 두 표기를 묶고, 판정 대기 목록을 낸다"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import score_predictions as S  # noqa: E402


def row(pid, **kw):
    r = {"pred_id": pid, "made_on": "2026-11-01", "thesis_id": "", "statement": "s", "metric": "m", "target": "t", "deadline": "2026-11-10",
         "probability": "0.6", "basis": "b", "resolved_on": "", "outcome": "", "notes": "", "owner": "치입", "origin": ""}
    r.update(kw)
    return r


class T(unittest.TestCase):
    def test_problems(self):
        shifted = row("P-3")
        shifted[None] = ["extra"]   # csv.DictReader가 남는 칸을 None 키에 담는다
        got = dict(S.problems([row("P-1"), row("P-2", outcome="1.21배", resolved_on="2026-11-11"), shifted, row("P-4", probability="60%"), row("P-5", owner="1차 판정")]))
        self.assertNotIn("P-1", got)
        self.assertIn("1 또는 0", got["P-2"])
        self.assertIn("칸 수", got["P-3"])
        self.assertIn("확률", got["P-4"])
        self.assertIn("주체", got["P-5"])

    def test_due_skips_bad_and_future(self):
        rows = [row("P-1"), row("P-2", deadline="2026-12-01"), row("P-3", resolved_on="2026-11-11", outcome="1"), row("P-4", probability="x")]
        self.assertEqual([r["pred_id"] for r in S.due(rows, date(2026, 11, 24))], ["P-1"])

    def test_brier_merges_owner_spellings(self):
        rows = [row("P-1", owner="치입", resolved_on="2026-11-11", outcome="1"), row("P-2", owner="Chiip", resolved_on="2026-11-11", outcome="0", probability="0.2"),
                row("P-3", owner="마스터", resolved_on="2026-11-11", outcome="1.21배")]
        by, total = S.brier(rows)
        self.assertEqual(set(by), {"Chiip"})
        self.assertEqual(by["Chiip"][1], 2)
        self.assertAlmostEqual(total[0], ((0.6 - 1) ** 2 + 0.2 ** 2) / 2)


if __name__ == "__main__":
    unittest.main()
