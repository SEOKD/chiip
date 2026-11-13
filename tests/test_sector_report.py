"""Analysis '섹터 핵심 지표' 절·섹터 데이터 원천 시험 (마스터 지시 2026-11-13 종목 범위 확대 4단계, ADR-029)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import sector_data as sd  # noqa: E402
import sector_view as sv  # noqa: E402

SK = {"lens": "health", "as_of": "3Q26",
      "kpis": [{"q": 7, "name": "매출총이익률", "value": 84.4, "unit": "%", "peer": 70.0, "period": "TTM", "source": "https://www.sec.gov/x"},
               {"q": 1, "name": "핵심 제품 매출 비중", "value": None, "unit": "%", "period": "3Q26", "source": ""}],
      "edge_struct": {"score": 6.5, "why": "동종보다 매출총이익률이 14%p 높다"}, "kill": "핵심 제품 처방 2분기 연속 감소"}


class View(unittest.TestCase):
    def test_none_or_missing_gives_no_section(self):
        self.assertIsNone(sv.section({}))
        self.assertIsNone(sv.section({"sector_kpis": {"none": "지주회사"}}))

    def test_section(self):
        s = sv.section({"sector_kpis": SK})
        self.assertEqual(s["h2"], "섹터 핵심 지표")
        table = next(b for b in s["blocks"] if b["type"] == "table")
        self.assertEqual(table["rows"][0][0].split("(")[0], "매출의 몇 %가 어느 제품·기기에서 나오나")   # 질문 번호 순
        self.assertEqual(table["rows"][0][2], "미확인")
        self.assertEqual(table["rows"][1][2], "84.4%")
        self.assertIn("6.5/10", s["blocks"][0]["text"])
        self.assertIn("미확인 1칸", s["blocks"][-1]["text"])
        self.assertEqual(s["_sources"], ["https://www.sec.gov/x"])

    def test_check_rejects(self):
        bad = {**SK, "kill": "", "kpis": [{"q": 1, "name": "x", "value": 3, "source": ""}]}
        with self.assertRaises(SystemExit):
            sv.section({"sector_kpis": bad})
        with self.assertRaises(SystemExit):
            sv.section({"sector_kpis": {**SK, "lens": "nope"}})


class Data(unittest.TestCase):
    def test_ai_chain_is_not_applicable(self):
        self.assertTrue(sd.run("co-ttm", "TTMI", "TTM Technologies", get=lambda u: {})[0].startswith("해당 없음"))

    def test_fdic_exact_holding_name(self):
        rows = {"data": [{"data": {"NAME": "Bank A", "NAMEHCR": "PALOMAR ENTERPRISES LLC"}}, {"data": {"NAME": "Bank B", "NAMEHCR": "PALOMAR INC"}}]}
        got = sd.fdic("Palomar Holdings, Inc.", get=lambda u: rows)
        self.assertEqual([r["NAME"] for r in got], ["Bank B"])

    def test_openfda_filters_other_sponsors(self):
        def get(u):
            if "drugsfda" in u:
                return {"results": [{"sponsor_name": "XERIS PHARMS", "application_number": "NDA1", "products": [{"brand_name": "GVOKE"}],
                                     "submissions": [{"submission_status_date": "20250314", "submission_type": "SUPPL", "submission_status": "AP"}]},
                                    {"sponsor_name": "OTHER CO", "application_number": "NDA2", "products": [], "submissions": [{"submission_status_date": "20260101"}]}]}
            return {"results": []}
        got = sd.openfda("Xeris Biopharma Holdings, Inc.", get=get)
        self.assertEqual(len(got), 1)
        self.assertIn("GVOKE", got[0][2])

    def test_life_tools_uses_industrials_lens(self):
        self.assertEqual(sd.LENS_OF["life_tools"], "industrials")


if __name__ == "__main__":
    unittest.main()
