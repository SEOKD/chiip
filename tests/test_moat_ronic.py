"""계속가치 RONIC ← 리포트 해자 판정(ADR-040, 마스터 승인 2026-11-15) — 해자 점수·10년차 ROIC 상한·출구 배수 점검·멀티플 이중 반영 방지"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
import dcf  # noqa: E402
import multiples  # noqa: E402
import plus  # noqa: E402

TABLE = ({"강함": 0.04, "보통": 0.015, "약함": -0.015, "해당 없음": 0.0}, 0.12)


def item(v, ev="콜·10-K 근거"):
    return {"kind": "전환 비용", "verdict": v, "claim": "c", "evidence": ev, "quant": "q", "falsifier": "f"}


def drivers(**kw):
    d = {"rev0": 100.0, "growth": [0.08] * 10, "margin": [0.25] * 10, "tax": 0.25, "s2c": 2.0, "ic0": 60.0, "wacc": 0.10, "g_term": 0.035,
         "ronic": None, "net_debt": 0.0, "shares": 1.0, "midyear": True}
    d.update(kw)
    return d


class TestMoatScore(unittest.TestCase):
    def test_score_and_label(self):
        s = plus.moat_score({"moat": {"items": [item("강함"), item("강함"), item("강함")]}}, TABLE)
        self.assertEqual((s["score"], s["label"], s["n"]), (1.0, "넓은 해자", 3))
        s = plus.moat_score({"moat": {"items": [item("강함"), item("보통"), item("보통")]}}, TABLE)
        self.assertAlmostEqual(s["score"], 0.583, places=3)
        self.assertEqual(s["label"], "좁은 해자")

    def test_aliases_and_skips(self):   # 11/15 점검: '중간'·'약점'·'약화 중' 10건이 점수표에 없어 0점이었다
        s = plus.moat_score({"moat": {"items": [item("중간"), item("약점"), item("미확인"), item("강함", ev="")]}}, TABLE)
        self.assertEqual(s["n"], 2)                     # 미확인·근거 없는 항목은 세지 않는다
        self.assertEqual(s["score"], 0.0)               # 보통 + 약함 = 0
        self.assertEqual(plus.verdict({"verdict": "약화 중"}), "약함")

    def test_no_items(self):
        s = plus.moat_score({}, TABLE)
        self.assertEqual((s["score"], s["n"], s["label"]), (0.0, 0, "해자 근거 없음"))


class TestRonicCap(unittest.TestCase):
    def test_moat_ronic_capped_by_terminal_roic(self):   # LTH형: 10년차 ROIC 9% < WACC면 해자가 있어도 RONIC = WACC
        d = drivers(ic0=400.0, ronic=0.18, ronic_cap=True)
        rows, _ = dcf.project(d)
        self.assertLess(rows[-1]["roic"], d["wacc"])
        self.assertAlmostEqual(dcf.effective_ronic(d, rows), d["wacc"])
        self.assertAlmostEqual(dcf.value(d)["ev"], dcf.value(drivers(ic0=400.0))["ev"])

    def test_moat_ronic_capped_at_roic_not_above(self):
        d = drivers(ronic=0.50, ronic_cap=True)
        rows, _ = dcf.project(d)
        self.assertAlmostEqual(dcf.effective_ronic(d, rows), max(d["wacc"], rows[-1]["roic"]))

    def test_explicit_spread_is_not_capped(self):
        d = drivers(ic0=400.0, ronic=0.18)   # ronic_cap 없음 = 동인에 명시한 ronic_spread
        rows, _ = dcf.project(d)
        self.assertAlmostEqual(dcf.effective_ronic(d, rows), 0.18)

    def test_moat_raises_value_when_roic_allows(self):
        lo, hi = dcf.value(drivers()), dcf.value(drivers(ronic=0.16, ronic_cap=True))
        self.assertGreater(hi["ev"], lo["ev"])
        self.assertLess(hi["ep_gap"], 1e-9)            # 경제적 이익 항등은 그대로


class TestExitCheck(unittest.TestCase):
    C = {"exit_check": {"industry_ev_ebit": {"semiconductor": 44.3, "legal_finance": None}, "default_ev_ebit": 25.7}}

    def test_floor_and_no_low_warning(self):   # 보수 가정(RONIC = WACC)의 낮은 출구 배수는 경고하지 않는다
        d = drivers()
        mult, (floor, ind), warn = plus.exit_check(dcf.value(d), d, "semiconductor", self.C)
        self.assertAlmostEqual(floor, round(0.75 / 0.10, 1))
        self.assertAlmostEqual(mult, 0.75 / 0.10, places=6)
        self.assertEqual(ind, 44.3)
        self.assertIsNone(warn)

    def test_aggressive_terminal_warns(self):
        d = drivers(wacc=0.05, g_term=0.04, ronic=0.40)
        mult, _, warn = plus.exit_check(dcf.value(d), d, "unknown_industry", self.C)
        self.assertGreater(mult, 25.7)
        self.assertIn("공격적", warn)

    def test_finance_not_checked(self):
        d = drivers(wacc=0.05, g_term=0.04, ronic=0.40)
        self.assertIsNone(plus.exit_check(dcf.value(d), d, "legal_finance", self.C)[2])


class TestNoDoubleCount(unittest.TestCase):
    def test_rational_multiple_uses_moat_neutral_dcf(self):   # 해자는 멀티플 선정의 해자 프리미엄으로 한 번만
        dp = {"tax": 0.25, "financials": {"rev_ttm": 100.0}, "profile": {"debt": 0, "cash": 0}, "multiples_now": {}, "peers": []}
        seen = []
        real = dcf.value

        def spy(d, *a, **k):
            seen.append((d.get("ronic"), d.get("ronic_cap")))
            return real(d, *a, **k)
        with mock.patch.object(multiples.dcf, "value", side_effect=spy):
            multiples.analyze(dp, drivers(ronic=0.18, ronic_cap=True), 500.0, 0.10, 0.035)
        self.assertIn((None, False), seen)
        self.assertNotIn((0.18, True), seen)


if __name__ == "__main__":
    unittest.main()
