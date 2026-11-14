"""Analysis 양식 전반 고도화(ADR-041) — 시나리오 이익 연도 맞춤·동종 이상치·지금 배수 재계산·내러티브 점검·글 점검·표기"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for sub in ("scripts/valuation/v2", "scripts/tenbagger"):
    sys.path.insert(0, str(ROOT / sub))
import multiples  # noqa: E402
import narrative_view  # noqa: E402
import report_layout  # noqa: E402


class TestPeers(unittest.TestCase):
    def test_trim_outliers(self):   # FWONK: MSGS 369.9배가 p75를 끌었다
        peers = [{"ticker": t, "ev_ebitda_fwd": v} for t, v in (("A", 18.0), ("B", 20.0), ("C", 22.0), ("D", 73.3), ("E", 369.9))]
        out, cut = multiples.trim_peers(peers)
        self.assertEqual([p["ev_ebitda_fwd"] for p in out], [18.0, 20.0, 22.0, None, None])
        self.assertEqual(len(cut), 2)

    def test_refresh_now_at_engine_price(self):   # DELL: 스냅숏 P/E가 오늘 가격과 23% 어긋났다
        dp = {"multiples_now": {"pe_fwd": 16.0}, "forward": {"ntm": {"eps": 20.0}}, "unit": "B$"}
        now, notes = multiples.refresh_now(dp, 250.0, None)
        self.assertAlmostEqual(now["pe_fwd"], 12.5)
        self.assertTrue(notes)
        same, n2 = multiples.refresh_now(dp, 330.0, None)   # 3% 차이는 그대로
        self.assertEqual((same["pe_fwd"], n2), (16.0, []))


class TestHorizon(unittest.TestCase):
    DP = {"forward": {"ntm": {"eps": 4.97}, "horizons": {"2": {"eps": 5.42}, "3": {"eps": 6.22}}}, "multiples_now": {"pe_fwd": 13.9, "pe_fwd2": 12.8}}
    MM = {"horizons": [{"h": 1, "peer_range": {"p50": 20.0}}, {"h": 2, "peer_range": {"p50": 17.0}}]}

    def test_ntm_case_keeps_one_year(self):
        self.assertEqual(report_layout.case_horizon(self.DP, self.MM, {"eps": 5.0}, False)[:2], (1, 1.0))

    def test_two_year_case_uses_two_year_multiple(self):   # PRIM형: 기본 EPS가 2년 뒤 컨센서스
        h, ratio, why = report_layout.case_horizon(self.DP, self.MM, {"eps": 5.6}, False)
        self.assertEqual(h, 2)
        self.assertAlmostEqual(ratio, 17.0 / 20.0)
        self.assertIn("2년 뒤", why)

    def test_fallback_to_own_multiples(self):
        h, ratio, _ = report_layout.case_horizon(self.DP, {"horizons": []}, {"eps": 5.6}, False)
        self.assertAlmostEqual(ratio, 12.8 / 13.9)


def rev(rows):
    return {"revisions": {"rows": [{"metric": "EPS", "period": p, "from": f, "to": t} for p, f, t in rows]}}


class TestNarrative(unittest.TestCase):
    def test_stage_must_be_one_of_six(self):   # PRIM '붕괴 뒤 바닥 다지기'가 내러티브 요인에서 0으로 처리됐다
        b, _ = narrative_view.audit({"narrative": {"stage": "붕괴 뒤 바닥 다지기", "as_of": "2026-11-10"}})
        self.assertTrue(b)

    def test_stale_after_call(self):   # CBRS 11/7 내러티브, 11/12 콜
        b, _ = narrative_view.audit({"narrative": {"stage": "확산", "as_of": "2026-11-07"}, "call": {"date": "2026-11-12"}})
        self.assertIn("어닝콜", b[0])

    def test_stage_vs_revisions_warns(self):
        _, w = narrative_view.audit({"narrative": {"stage": "확산", "as_of": "2026-11-13", "factors": [{"status": "강화", "source": "콜"}]},
                                     "consensus": rev([("Q1", 1.0, 0.8), ("Q2", 1.0, 0.7)])})
        self.assertTrue(any("하향" in x for x in w))

    def test_negative_eps_revision_sign(self):   # 코어위브: 적자 확대가 +78%로 읽혔다
        r, _ = narrative_view.revision_pct(rev([("Q1", -0.5, -0.9), ("Q2", -0.4, -0.7)]))
        self.assertLess(r, 0)
        r2, _ = narrative_view.revision_pct(rev([("Q1", 1.0, 1.2)]))
        self.assertAlmostEqual(r2, 0.2)


class TestText(unittest.TestCase):
    R = {"mcap": 40.56, "unit": "B$", "upside": {"implied_cagr": 0.15, "base_cagr": 0.08}, "scenarios": {"base": {"v0": 0.83}}}

    def test_market_half_believes_contradicts_engine(self):   # PRIM 제목
        d = {"title": "2027년 EPS 반등을 시장이 반만 믿는다(EPS $5.4)", "verdict": {}}
        self.assertTrue(report_layout.text_checks(d, self.R, {}))

    def test_misjudge_without_number_blocked(self):
        self.assertTrue(report_layout.text_checks({"verdict": {"view": "시장이 이 변화를 간과하고 있다."}}, self.R, {}))

    def test_mcap_basis(self):   # CRWV: 글 $33.5B vs 엔진 $40.56B
        bad = {"verdict": {"view": "주가 $60, 시가총액 $33.5B다."}}
        ok = {"verdict": {"view": "시가총액 $33.5B(기본 주식 기준)다."}}
        self.assertTrue(report_layout.text_checks(bad, self.R, {}))
        self.assertFalse(report_layout.text_checks(ok, self.R, {}))

    def test_low_price_decimals(self):
        self.assertEqual(report_layout.price_fmt("$", 4.3, 7.52), "$4.30")
        self.assertEqual(report_layout.price_fmt("$", 86.0, 101.0), "$86")


if __name__ == "__main__":
    unittest.main()
