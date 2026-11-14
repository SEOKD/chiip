"""밸류에이션 신뢰성 고도화(ADR-039, 마스터 지시 2026-11-14 "Analysis의 Valuation Model을 점검하라 … 신뢰성을 높이기 위해 고도화")
① 회계연도 할인 시점(fy_offset) ② DCF 신뢰 점검(산정 불가면 목표주가·등급에서 DCF 제외) ③ 하류(목표주가·등급·장부·매수 판단) 일관"""
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("scripts/valuation/v2", "scripts/tenbagger", "scripts/discovery"):
    sys.path.insert(0, str(ROOT / sub))
import dcf  # noqa: E402
import fiscal  # noqa: E402
import run  # noqa: E402


def drivers(**kw):
    d = {"rev0": 100.0, "growth": [0.10] * 10, "margin": [0.20] * 10, "tax": 0.25, "s2c": 2.0, "ic0": 80.0, "wacc": 0.09, "g_term": 0.03,
         "ronic": None, "net_debt": 10.0, "shares": 1.0, "midyear": True}
    d.update(kw)
    return d


class TestTiming(unittest.TestCase):
    def test_zero_offset_equals_old_midyear(self):
        a, b = dcf.value(drivers()), dcf.value(drivers(fy_offset=0.0))
        self.assertAlmostEqual(a["ev"], b["ev"], places=9)
        self.assertAlmostEqual(a["cv_share"], b["cv_share"], places=9)

    def test_remaining_current_year_is_counted_and_later_years_pushed_out(self):
        base = dcf.value(drivers())["ev"]
        late = dcf.value(drivers(fy_offset=0.95))   # AMAT형: rev0 해가 거의 1년 남았다
        self.assertGreater(late["stub"], 0)
        self.assertLess(late["ev"], base)            # 1년차 이후가 0.95년 늦어진 효과가 남은 해 몫보다 크다(성장·계속가치 비중)
        # 남은 몫을 빼면 정확히 0.95년 더 할인한 값
        pushed = (late["ev"] - late["stub"]) * (1.09 ** 0.95)
        self.assertAlmostEqual(pushed, base, places=6)

    def test_negative_offset_drops_elapsed_part_of_year_one(self):
        d = drivers(fy_offset=-0.25)
        r = dcf.value(d)
        f1, tau1 = dcf.timing(10, -0.25, True)[0]
        self.assertAlmostEqual(f1, 0.75)
        self.assertAlmostEqual(tau1, 0.375)
        self.assertEqual(r["stub"], 0.0)

    def test_ep_identity_still_holds(self):
        self.assertLess(dcf.value(drivers(fy_offset=0.4))["ep_gap"], 1e-9)


class TestFiscal(unittest.TestCase):
    def co(self, prov, **kw):
        return {"provenance": {"rev0": prov}, "ticker": "ZZZZ", "region_mix": {"US": 1.0}, "market": {"date": "2026-11-14"}, **kw}

    def test_label_from_provenance_and_fy_end(self):
        t = fiscal.offset(self.co("컨센서스 FY2027 46.7", fy_end="10-26"))
        self.assertEqual(t["end"], "2027-10-26")
        self.assertAlmostEqual(t["offset"], (date(2027, 10, 26) - date(2026, 11, 14)).days / 365.25, places=4)

    def test_hand_made_drivers_match_consensus_year(self):   # AMAT — provenance 없음
        co = self.co("", rev0=46.5, fy_end="10-26")
        t = fiscal.offset(co, {"consensus": {"rev": {"FY2027": 46.7, "FY2028": 55.0}}})
        self.assertEqual(t["end"], "2027-10-26")

    def test_currency_region_beats_region_mix(self):   # TOWA region_mix 'ASIA' — 통화 ¥면 3월 결산 기본값
        md, src = fiscal.fy_end({"ticker": "9999X", "region_mix": {"ASIA": 1.0}}, {"currency_symbol": "¥"})
        self.assertEqual(md, "03-31")
        self.assertIn("JP", src)

    def test_implausible_offset_is_not_applied(self):   # 아직 시작도 안 한 해(1년 넘게 남음)면 라벨 해석 의심
        t = fiscal.offset(self.co("컨센서스 FY2028 10", fy_end="12-31"))
        self.assertIsNone(t["offset"])

    def test_ttm_uses_last_quarter_end(self):
        t = fiscal.offset(self.co("TTM 매출(컨센서스 없음)"), {"quarters_hist": {"q": [{"period": "2026-09-30"}]}})
        self.assertEqual(t["end"], "2026-09-30")
        self.assertLess(t["offset"], 0)


def scen(bear, base, bull):
    return {"bear": {"v0": bear}, "base": {"v0": base}, "bull": {"v0": bull}}


def specs(gb, g, gu, mb=0.1, m=0.2, mu=0.3):
    return {k: {"growth": {"start": x}, "margin": {"target": y}} for k, x, y in (("bear", gb, mb), ("base", g, m), ("bull", gu, mu))}


class TestQuality(unittest.TestCase):
    def setUp(self):
        self.base = dcf.value(drivers())

    def test_normal(self):
        q = run.quality(scen(0.8, 1.0, 1.3), self.base, None, {}, specs(0.0, 0.1, 0.2))
        self.assertEqual((q["status"], q["usable"]), ("정상", True))

    def test_broken_inputs_are_unusable(self):   # 46주차 전 브로드컴: 강세 성장 2.5% < 기본 60.5%
        q = run.quality(scen(0.2, 2.9, 0.25), self.base, None, {}, specs(-0.014, 0.605, 0.025))
        self.assertFalse(q["usable"])
        self.assertIn("입력 순서", q["flags"][0])

    def test_value_order_flip_with_ordered_inputs_is_only_a_warning(self):   # ROIC < WACC면 성장이 가치를 깎는다
        q = run.quality(scen(0.24, 0.05, 2.8), self.base, None, {}, specs(0.02, 0.2, 0.49))
        self.assertTrue(q["usable"])
        self.assertEqual(q["status"], "주의")

    def test_loss_forever_is_unusable(self):
        loss = dcf.value(drivers(margin=[-0.3] * 10))
        q = run.quality(scen(-2, -1, -0.5), loss, None, {}, specs(0.0, 0.1, 0.2))
        self.assertFalse(q["usable"])
        self.assertTrue(any("NOPAT" in x for x in q["flags"]))

    def test_exit_warning_kept_apart(self):
        q = run.quality(scen(0.8, 1.0, 1.3), self.base, "내포 출구 EV/EBIT 6.5배가 업종 범위 8~25배 밖", {}, specs(0.0, 0.1, 0.2))
        self.assertEqual(q["status"], "정상")
        self.assertIn("출구", q["exit"])


class TestDownstream(unittest.TestCase):
    CFG = {"rating": {"strong_buy": {"upside": 0.40, "rr": 3.0, "dcf_min": 0.0}, "buy": {"upside": 0.15, "rr": 1.5, "dcf_min": -0.5},
                      "neutral": {"upside": -0.10}, "sell": {"upside": -0.30}}}

    def test_rating_without_dcf(self):
        import report_layout
        self.assertEqual(report_layout.rating(0.6, 4.0, None, self.CFG), "Buy")          # 교차 확인 없이 Strong Buy는 없다
        self.assertEqual(report_layout.rating(0.6, 4.0, 0.1, self.CFG), "Strong Buy")
        self.assertEqual(report_layout.rating(0.2, 2.0, None, self.CFG), "Buy")
        self.assertEqual(report_layout.rating(0.2, 2.0, -0.8, self.CFG), "Neutral")

    def test_ledger_rule_matches_report_rule(self):
        import rating_ledger
        import report_layout
        for args in ((0.6, 4.0, None), (0.6, 4.0, 0.1), (0.2, 2.0, None), (0.2, 2.0, -0.8), (-0.2, 1.0, None)):
            self.assertEqual(rating_ledger.rule(*args, self.CFG["rating"]), report_layout.rating(*args, self.CFG))

    def test_target_drops_dcf_factor(self):
        import target_price
        s = {"price": 100.0, "bear": 70.0, "base": 100.0, "bull": 140.0, "weighted": 105.0,
             "cases": [{"name": "약세", "multiple": 9.0, "eps": 7.8, "prob": 0.25}, {"name": "기본", "multiple": 12.0, "eps": 8.3, "prob": 0.5},
                       {"name": "강세", "multiple": 15.0, "eps": 9.3, "prob": 0.25}]}
        cfg = {"weights": {"scenario": 0.35, "dcf": 0.20, "chart": 0.20, "narrative": 0.25}, "narrative_room": {"확산": 0.6}, "judge_cap": 0.25,
               "round_above": 20, "chart": {"near_high": 0.95, "min_gap": 0.01}}
        pt = target_price.build(s, None, 0.10, "확산", None, [], 0.0, 1.0, cfg)
        keys = [x["key"] for x in pt["factors"]]
        self.assertNotIn("dcf", keys)
        self.assertAlmostEqual(sum(x["weight"] for x in pt["factors"]), 1.0)
        with_dcf = target_price.build(s, 0.2, 0.10, "확산", None, [], 0.0, 1.0, cfg)   # 무의미하게 낮은 DCF가 목표를 약세 쪽으로 끌던 경우
        self.assertGreater(pt["target"], with_dcf["target"])

    def test_buy_call_handles_missing_dcf(self):
        import buy_call
        d = {"verdict": {"price": 50.0, "bear": 40.0, "bull": 70.0, "dcf_up": None}}
        self.assertIsNone(buy_call.scenario(d)[3])


if __name__ == "__main__":
    unittest.main()
