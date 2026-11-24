"""'고객의 지출 예산' 렌즈(마스터 지시 2026-11-13 — 옛 'CAPEX 낙수효과'를 사업별 CAPEX·OPEX 노출로)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import narrative_view as nv  # noqa: E402

LENS = {"lens": "고객의 지출 예산", "change": "고객 마케팅 예산에 노출", "evidence": "10-Q", "falsifier": "광고 예산 축소",
        "budgets": [{"business": "Grow(광고)", "budget": "OPEX", "line": "앱 개발사 이용자 확보 광고비", "share": 0.7, "driver": "모바일 게임 UA 예산"},
                    {"business": "Create(엔진 구독)", "budget": "OPEX", "line": "개발 도구 소프트웨어 예산"}]}


class TestBudgetLens(unittest.TestCase):
    def test_lens_renamed(self):
        self.assertIn("고객의 지출 예산", nv.LENSES)
        self.assertNotIn("CAPEX 낙수효과", nv.LENSES)

    def test_box_shows_per_business_budget(self):
        box = next(b for b in nv.lens_boxes({"lenses": [LENS]}) if b["title"] == "고객의 지출 예산")
        row = dict(box["lines"])["사업별 예산"]
        # 비중(결론)부터, 분류마다 한 줄(dffc9a08 — '매출의 59%: 사업 — 고객 CAPEX(…) · 동인: …', 비중 큰 순)
        self.assertIn("**매출의 70%**: Grow(광고) — 고객 OPEX(앱 개발사 이용자 확보 광고비)", row)
        self.assertIn("비중 미확인: Create(엔진 구독) — 고객 OPEX", row)
        self.assertLess(row.index("매출의 70%"), row.index("비중 미확인"))

    def test_legacy_name_still_read_and_flags_missing_split(self):
        box = next(b for b in nv.lens_boxes({"lenses": [{"lens": "CAPEX 낙수효과", "change": "해당 없음(소프트웨어)"}]}) if b["title"] == "고객의 지출 예산")
        self.assertEqual(dict(box["lines"])["사업별 예산"], "사업별 CAPEX·OPEX 구분 미확인")


if __name__ == "__main__":
    unittest.main()
