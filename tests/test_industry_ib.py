"""산업 리포트 IB 요소(2026-11-15 마스터 지시 "IB 리서치 하우스의 접근 방법과 사고 논리 … 양식을 고도화하라")"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "industry"))
import logic as LG  # noqa: E402
import industry_html as IH  # noqa: E402

IB = {"takeaways": ["a", "b", "c"],
      "estimates": [{"company": f"C{i}", "metric": "매출", "period": "FY27", "chiip": 110, "street": 100, "basis": "물량×ASP", "source": "Fiscal.ai·TradingView"} for i in range(3)],
      "revisions": [{"metric": "FY27 EPS", "window": "90일", "up": 12, "down": 3, "source": "s"}],
      "valuation_history": [{"name": "동종 중앙값", "multiple": "Fwd P/E", "now": 30, "avg": 25, "low": 15, "high": 40, "years": 5, "source": "s"}],
      "sensitivity": [{"driver": "ASP", "shock": "+10%", "metric": "EPS", "impact": "+18%", "basis": "영업 레버리지"}],
      "exposure": [{"name": n, "lever": "높음", "direction": "+", "why": "w"} for n in "xyz"],
      "positioning": [{"indicator": "공매도 비율", "value": "미확인", "read": "-", "source": "-"}]}


class TestIB(unittest.TestCase):
    def test_gate_requires_after_date(self):
        c = LG.cfg()
        self.assertEqual(LG.ib_gate({"date": "2026-11-15"}, "weekly", {}, c), [])     # 이전 발행분 면제
        bad = LG.ib_gate({"date": "2026-11-16"}, "weekly", {}, c)
        for k in ("takeaways", "estimates", "revisions", "valuation_history", "sensitivity", "exposure", "positioning"):
            self.assertTrue(any(k in b for b in bad), k)
        self.assertEqual(LG.ib_gate({"date": "2026-11-16"}, "weekly", IB, c), [])

    def test_estimate_needs_basis(self):
        L = dict(IB, estimates=[dict(IB["estimates"][0], basis="")] * 3)
        self.assertTrue(any("basis" in b for b in LG.ib_gate({"date": "2026-11-16"}, "weekly", L, LG.cfg())))

    def test_sections_math(self):
        S = LG.ib_sections(IB)
        self.assertEqual(S["estimates"][0]["rows"][0][5], "+10.0%")
        self.assertEqual(S["revisions"][0]["rows"][0][4], "+60%")
        self.assertEqual(S["valuation_history"][0]["rows"][0][6], "60%")

    def test_cycle_label(self):
        base = {"title": "t", "date": "2026-11-15", "industry": "i", "event": "e", "sections": [], "sources": []}
        self.assertIn("주간 산업", IH.render(dict(base, cycle="weekly")))
        self.assertNotIn("사건 때 심층", IH.render(dict(base, cycle="weekly")))
        self.assertIn("사건 때 심층", IH.render(base))


if __name__ == "__main__":
    unittest.main()
