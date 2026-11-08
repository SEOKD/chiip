"""다시 병합해도 Proviser 정정이 남는다 (마스터 지시 2026-11-08)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
import v2_to_report as v  # noqa: E402

FIX = {"h2": "정정 기록 — Chiip Proviser 23:55", "blocks": [{"type": "table", "headers": ["무엇을(전 → 후)", "왜", "근거"],
       "rows": [["'6/3 종가 고점 $479' → '6/2 종가 고점 $482'", "종가 고점은 6/2", "일봉"], ["'6월 고점 $495' 2곳 → '6월 장중 고점 $495'", "기준 혼용", "일봉"]]}]}


class TestCorrections(unittest.TestCase):
    def test_carry_and_reapply(self):
        old = {"sections": [{"h2": "내러티브", "blocks": []}, FIX], "corrections": [{"from": "−66%", "to": "−65%"}]}
        m = v.carry_corrections(old, {"sections": [{"h2": "체크리스트", "blocks": []}]})
        self.assertEqual([s["h2"] for s in m["sections"]], ["체크리스트", FIX["h2"]])
        self.assertEqual(len(m["corrections"]), 3)
        d = {"verdict": {"view": "6/3 종가 고점 $479에서 −66%다. 6월 고점 $495"}, "summary": [], "sections": m["sections"], "corrections": m["corrections"]}
        self.assertEqual(v.apply_corrections(d), [])
        self.assertEqual(d["verdict"]["view"], "6/2 종가 고점 $482에서 −65%다. 6월 장중 고점 $495")
        self.assertIn("'6/3 종가 고점 $479'", d["sections"][-1]["blocks"][0]["rows"][0][0])   # 정정 기록 표는 그대로

    def test_idempotent_and_miss(self):
        d = {"verdict": {"view": "6월 장중 고점 $495"}, "sections": [], "corrections": [{"from": "고점 $495", "to": "장중 고점 $495"}, {"from": "없는 문장", "to": "없는 정정"}]}
        miss = v.apply_corrections(d)
        self.assertEqual(d["verdict"]["view"], "6월 장중 고점 $495")   # '전'이 '후'에 들어 있으면 다시 고치지 않는다
        self.assertEqual([x["from"] for x in miss], ["없는 문장"])


if __name__ == "__main__":
    unittest.main()
