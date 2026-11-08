"""로비 내역 결론 규칙 (마스터 지시 2026-11-03)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar" / "usgov"))
import lobby_watch as lw  # noqa: E402


class TestVerdict(unittest.TestCase):
    def test_no_lda_is_unknown_even_with_other_hits(self):
        self.assertEqual(lw.verdict({"lda": {"status": "키 없음", "rows": []}}), "미확인")

    def test_lda_result(self):
        self.assertEqual(lw.verdict({"lda": {"status": "ok", "rows": [{}]}}), "로비 등록 있음")
        self.assertIn("없음", lw.verdict({"lda": {"status": "ok", "rows": []}}))


class TestHouse(unittest.TestCase):
    """하원 LD 분기 집계(Easyconomics) — lda.gov 차단 대체(2026-11-08)"""
    MCP = {"as_of": "2026-11-08", "source": "house_ld", "ticker": "NVDA",
           "quarters": [{"year": 2026, "quarter": 3, "total_usd": 2590000.0, "self_reported": 2150000.0, "outside_income": 440000.0,
                         "top_issue_codes": [{"code": "TRD", "count": 5}]}]}

    def test_rows_and_verdict(self):
        rows = lw.house_rows(self.MCP, "nvda")
        self.assertEqual(rows[0]["total_usd"], 2590000.0)
        self.assertEqual(rows[0]["issues"], ["TRD 5"])
        self.assertIn("로비 지출 있음", lw.verdict({"lda": {"status": "키 없음", "rows": []}, "house": {"status": "ok", "rows": rows}}))

    def test_outside_universe_stays_unknown(self):
        self.assertIsNone(lw.house_rows({**self.MCP, "ticker": "AVGO"}, "PSIX"))   # 다른 티커 결과면 쓰지 않는다
        self.assertEqual(lw.verdict({"lda": {"status": "키 없음", "rows": []}, "house": {"status": "유니버스 밖", "rows": []}}), "미확인")


if __name__ == "__main__":
    unittest.main()
