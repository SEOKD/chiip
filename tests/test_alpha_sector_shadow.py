"""알파 섹터 보정 그림자·채택 관문 시험 (마스터 지시 2026-11-13 종목 범위 확대 3단계, ADR-028)"""
import random
import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "alpha"))
import sector_shadow as ss  # noqa: E402

W = {"upside": 0.30, "gap": 0.30, "bottleneck": 0.20, "asymmetry": 0.20}
C = {"edge_sources": ["card", "judgment", "bottleneck"], "min_sector_n": 3, "blend": 0.30, "top_pct": 0.90,
     "gate": {"min_days": 28, "horizon_td": 5, "min_obs": 20, "ic_margin": 0.03, "halves": True}}
AI = {"ai_compute"}


def rows():
    comp = lambda b: {"upside": 6, "gap": 6, "bottleneck": b, "asymmetry": 5}  # noqa: E731
    return {"a1": {"total": 5.9, "components": comp(8)}, "a2": {"total": 5.5, "components": comp(6)},
            "h1": {"total": 4.9, "components": comp(2)}, "h2": {"total": 4.7, "components": comp(1)}, "h3": {"total": 4.5, "components": comp(1)},
            "u1": {"total": 5.0, "components": comp(5)}}


TAG = {"a1": "ai_compute", "a2": "ai_compute", "h1": "health", "h2": "health", "h3": "health", "u1": None}.get


class Shadow(unittest.TestCase):
    def test_ai_and_unknown_keep_bottleneck(self):
        out = ss.compute(rows(), W, C, TAG, AI.__contains__, {"a1": 2.0}, {})
        self.assertEqual(out["a1"]["s1"], round(0.3 * 6 + 0.3 * 6 + 0.2 * 8 + 0.2 * 5, 2))
        self.assertEqual(out["a1"]["edge_src"], "bottleneck")    # AI 밸류체인은 카드가 있어도 병목 그대로
        self.assertEqual(out["u1"]["edge_src"], "bottleneck")    # 미분류도 그대로

    def test_non_ai_priority_card_then_judgment_then_fallback(self):
        out = ss.compute(rows(), W, C, TAG, AI.__contains__, {"h1": 8.0}, {"h1": 3.0, "h2": 7.0})
        self.assertEqual((out["h1"]["edge"], out["h1"]["edge_src"]), (8.0, "card"))
        self.assertEqual((out["h2"]["edge"], out["h2"]["edge_src"]), (7.0, "judgment"))
        self.assertEqual((out["h3"]["edge"], out["h3"]["edge_src"]), (1, "bottleneck(대체)"))
        self.assertGreater(out["h1"]["s1"], rows()["h1"]["total"])

    def test_sector_pct_and_s2(self):
        out = ss.compute(rows(), W, C, TAG, AI.__contains__, {}, {})
        self.assertEqual(out["h1"]["sector_pct"], 1.0)           # 헬스케어 3개 안에서 1등
        self.assertTrue(out["h1"]["sector_top"])
        self.assertFalse(out["a1"]["sector_top"])                # AI 섹터는 2개뿐 → 섹터 안 순위 없음(전체 백분위)
        self.assertAlmostEqual(out["h1"]["s2"], round(0.7 * out["h1"]["s1"] + 3.0, 2))


class Gate(unittest.TestCase):
    def series(self, start, n, drift):
        return [[(start + timedelta(days=i)).isoformat(), 100 * (1 + drift) ** i] for i in range(n)]

    def make(self, s_good=True):
        random.seed(1)
        d0 = date(2026, 10, 1)
        prices, rows = {"SPY": self.series(d0, 80, 0.0)}, []
        for k in range(30):
            q = random.random()                                   # 진짜 품질 — 앞 수익을 정한다
            prices[f"T{k}"] = self.series(d0, 80, 0.004 * (q - 0.5))
            for day in range(0, 40, 5):
                d = (d0 + timedelta(days=day)).isoformat()
                v1 = random.random() * 10                          # v1은 잡음
                s = q * 10 if s_good else random.random() * 10
                rows.append({"date": d, "id": f"us-t{k}", "ai": "False", "v1": v1, "s1": s, "s2": s})
        return rows, prices

    def test_hold_before_four_weeks(self):
        rows, prices = self.make()
        g = ss.gate(date(2026, 10, 20), C, rows, prices, lambda i: i[3:].upper())
        self.assertEqual(g["verdict"], "판정 보류")

    def test_adopt_when_better_in_both_halves(self):
        rows, prices = self.make(True)
        g = ss.gate(date(2026, 12, 20), C, rows, prices, lambda i: i[3:].upper())
        self.assertTrue(g["verdict"].startswith("채택 제안 가능"), g)

    def test_reject_when_not_better(self):
        rows, prices = self.make(False)
        g = ss.gate(date(2026, 12, 20), C, rows, prices, lambda i: i[3:].upper())
        self.assertEqual(g["verdict"], "기각 — v1 유지")

    def test_spearman(self):
        self.assertAlmostEqual(ss.spearman([1, 2, 3, 4, 5], [2, 4, 6, 8, 10]), 1.0)
        self.assertAlmostEqual(ss.spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1]), -1.0)


if __name__ == "__main__":
    unittest.main()
