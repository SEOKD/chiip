"""텐배거 판단 체계(ADR-050, 2026-11-21 마스터 지시) 오프라인 시험 — 10배 산술·유동성 국면·구루 교차 점검 관문·낙폭 재심사·성적표 오른쪽 꼬리"""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
import leads  # noqa: E402
import memo_check  # noqa: E402
import playbook as pb  # noqa: E402

CFG = pb.cfg()
SRC = "https://www.sec.gov/Archives/edgar/data/1/x.htm"


def good_pb():
    """통과 4 · 미달 1 · 미확인 1, 가장 약한 관점 = 미달 관점"""
    return {"horizon_years": 7,
            "views": {"runway": {"verdict": "pass", "why": "참조 시장 3배", "evidence": SRC},
                      "moat_returns": {"verdict": "pass", "why": "ROIC 18%", "evidence": "10-K 2025 Item 1"},
                      "reinvestment": {"verdict": "pass", "why": "증설 2건", "evidence": "knowledge/models/companies/us-xyz/datapack.json"},
                      "people": {"verdict": "unknown", "why": "위임장 미확인", "evidence": ""},
                      "change": {"verdict": "fail", "why": "2년 뒤 EPS가 줄어든다", "evidence": ""},
                      "mispricing": {"verdict": "pass", "why": "커버 2명", "evidence": SRC}},
            "dissent": {"view": "change", "why": "추정 하향"},
            "hold": {"kpis": ["수주잔고 YoY", "매출총이익률"], "rule": "가격만 −50%면 재심사"}}


class TestArithmetic(unittest.TestCase):
    DP = {"consensus": {"rev": {"FY2026": 100, "FY2028": 169}},
          "financials": {"ebit_ttm": 20, "invested_capital": 100, "capex_ttm": 12, "da_ttm": 4, "sbc_ttm": 1},
          "profile": {"price": 10, "shares_basic": 30}, "tax": 0.25,
          "forward": {"ntm": {"eps": 1.0}, "horizons": {"2": {"eps": 1.5}}}, "multiples_now": {"pe_fwd": 12}}

    def test_required_growth(self):
        self.assertAlmostEqual(pb.cagr(10, 5), 0.5849, 4)
        r = pb.required(CFG)
        self.assertAlmostEqual(r[10][10], 0.2589, 4)
        self.assertAlmostEqual(r[10][7], 0.3895, 4)
        self.assertAlmostEqual(r[2][5], CFG["arithmetic"]["double_5y"], 4)

    def test_two_engines(self):
        e = pb.two_engines(10, 5, 2)          # 배수가 2배로 재평가되면 이익은 5배면 된다
        self.assertEqual(e["eps_multiple"], 5.0)
        self.assertAlmostEqual(e["eps_cagr"], 0.3797, 4)

    def test_views_numbers(self):
        a = pb.arithmetic(self.DP, None, CFG)
        self.assertAlmostEqual(a["rev_path"]["cagr"], 0.30, 4)
        self.assertEqual(a["years_to_double"], 2.6)
        self.assertTrue(a["doubles_in_5y"])
        self.assertAlmostEqual(a["roic"], 0.15, 4)                  # 20 × (1 − 0.25) ÷ 100
        self.assertAlmostEqual(a["reinvest_rate"], 0.5333, 4)       # (12 − 4) ÷ 15
        self.assertAlmostEqual(a["sustainable_growth"], 0.08, 4)
        self.assertAlmostEqual(a["owner_earnings_yield"], 0.0467, 4)  # (15 − 1) ÷ 300
        self.assertAlmostEqual(a["eps_change_24m"], 0.5, 4)
        self.assertEqual(a["pe_fwd"], 12)

    def test_unknown_stays_none(self):
        a = pb.arithmetic({}, None, CFG)
        for k in ("roic", "reinvest_rate", "sustainable_growth", "owner_earnings_yield", "eps_change_24m", "years_to_double", "doubles_in_5y"):
            self.assertIsNone(a[k], k)
        self.assertNotIn("rev_path", a)
        text = "\n".join(pb.lines(a, ("미확인", "자료 없음")))
        self.assertIn("매출 경로 미확인", text)
        self.assertIn("ROIC 미확인", text)

    def test_ttm_fallback(self):
        a = pb.arithmetic({"financials": {"rev_growth_ttm": 0.10}}, None, CFG)
        self.assertEqual(a["rev_path"]["from"], "TTM")
        self.assertFalse(a["doubles_in_5y"])                       # 연 10% < 14.87%
        self.assertEqual(a["years_to_double"], 7.3)

    def test_lines_readable(self):
        text = "\n".join(pb.lines(pb.arithmetic(self.DP, None, CFG), ("중립", "10년물 20일 +5bp")))
        self.assertIn("5년 58.5%", text)
        self.assertIn("충족", text)
        self.assertIn("유동성 국면 중립", text)


class TestLiquidity(unittest.TestCase):
    def test_regimes(self):
        self.assertEqual(pb.liquidity(CFG, {"us10y": {"d20": 0.30}, "hy": {"d20": 0.0}})[0], "긴축")
        self.assertEqual(pb.liquidity(CFG, {"us10y": {"d20": 0.0}, "hy": {"d20": 0.45}})[0], "긴축")
        self.assertEqual(pb.liquidity(CFG, {"us10y": {"d20": -0.30}, "hy": {"d20": -0.05}})[0], "완화")
        self.assertEqual(pb.liquidity(CFG, {"us10y": {"d20": -0.30}, "hy": {"d20": 0.20}})[0], "중립")   # 금리는 내렸지만 신용이 벌어진다
        self.assertEqual(pb.liquidity(CFG, {"us10y": {"d20": 0.05}, "hy": {"d20": 0.10}})[0], "중립")

    def test_no_data_is_unknown(self):
        self.assertEqual(pb.liquidity(CFG, {})[0], "미확인")


class TestCheck(unittest.TestCase):
    def test_good_focus(self):
        fails, warns, s = pb.check(good_pb(), "focus", CFG)
        self.assertEqual(fails, [])
        self.assertEqual((s["pass"], s["fail"], s["unknown"], s["dissent"]), (4, 1, 1, "change"))

    def test_missing_block(self):
        fails, _, _ = pb.check(None, "focus", CFG)
        self.assertTrue(fails and "playbook 칸 없음" in fails[0])

    def test_pass_needs_evidence(self):
        d = good_pb()
        d["views"]["runway"]["evidence"] = "경영진이 그렇게 말했다"
        fails, _, _ = pb.check(d, "focus", CFG)
        self.assertTrue(any("근거" in f and "runway" in f for f in fails))

    def test_unknown_is_not_pass(self):
        d = good_pb()
        d["views"]["mispricing"] = {"verdict": "unknown", "why": "역DCF 미산정"}
        fails, _, s = pb.check(d, "focus", CFG)
        self.assertEqual(s["pass"], 3)
        self.assertTrue(any("통과 3개 < 4개" in f for f in fails))
        self.assertEqual(pb.check(d, "bench", CFG)[0], [])          # bench는 3개면 된다

    def test_moat_fail_blocks_focus(self):
        d = good_pb()
        d["views"]["moat_returns"] = {"verdict": "fail", "why": "ROIC 4%"}
        d["views"]["people"] = {"verdict": "pass", "why": "창업자 지분 22%", "evidence": "DEF 14A"}
        d["views"]["change"] = {"verdict": "pass", "why": "추정 상향", "evidence": SRC}
        d["dissent"] = {"view": "moat_returns", "why": "수익률이 자본비용 아래"}
        fails, _, s = pb.check(d, "focus", CFG)
        self.assertEqual(s["pass"], 5)                              # 다섯 관점이 통과해도
        self.assertTrue(any("focus 불가" in f for f in fails))       # 해자 미달이면 focus가 될 수 없다
        self.assertEqual(pb.check(d, "bench", CFG)[0], [])

    def test_dissent_and_hold_required(self):
        d = good_pb()
        d.pop("dissent")
        d["hold"] = {"kpis": ["수주잔고"]}
        fails, _, _ = pb.check(d, "focus", CFG)
        self.assertTrue(any("dissent" in f for f in fails))
        self.assertTrue(any("보유 규율" in f for f in fails))

    def test_dissent_on_passed_view_warns(self):
        d = good_pb()
        d["dissent"] = {"view": "runway", "why": "시장 크기 추정이 거칠다"}
        fails, warns, _ = pb.check(d, "focus", CFG)
        self.assertEqual(fails, [])
        self.assertTrue(any("가장 약한 관점" in w for w in warns))

    def test_horizon_range(self):
        for hz in (1, 12, None):
            d = good_pb()
            d["horizon_years"] = hz
            self.assertTrue(any("판단 기간" in f for f in pb.check(d, "focus", CFG)[0]), hz)

    def test_many_unknown_warns(self):
        d = good_pb()
        for k in ("runway", "reinvestment", "mispricing"):
            d["views"][k] = {"verdict": "unknown", "why": "미조사"}
        fails, warns, _ = pb.check(d, "bench", CFG)
        self.assertTrue(fails)
        self.assertTrue(any("미확인 4개" in w for w in warns))

    def test_rare_path_warns(self):
        d = good_pb()
        d.update(horizon_years=5, target_multiple=10)             # 5년 10배 = 연 58.5%
        fails, warns, s = pb.check(d, "focus", CFG)
        self.assertEqual(fails, [])                                # 경고일 뿐 실패가 아니다
        self.assertAlmostEqual(s["required_cagr"], 0.5849, 4)
        self.assertTrue(any("희소한 경로" in w for w in warns))
        d.update(horizon_years=10)                                 # 10년 10배 = 연 25.9%
        _, warns, s = pb.check(d, "focus", CFG)
        self.assertFalse(any("희소한 경로" in w for w in warns))
        self.assertAlmostEqual(s["required_cagr"], 0.2589, 4)
        self.assertIsNone(pb.check(good_pb(), "focus", CFG)[2]["required_cagr"])   # 목표 배수를 안 적으면 계산하지 않는다

    def test_config_is_consistent(self):
        self.assertEqual(set(CFG["views"]), {"runway", "moat_returns", "reinvestment", "people", "change", "mispricing"})
        self.assertTrue(set(CFG["gate"]["must_not_fail"]) <= set(CFG["views"]))
        self.assertLessEqual(CFG["gate"]["pass_min"]["bench"], CFG["gate"]["pass_min"]["focus"])
        for v in CFG["views"].values():
            self.assertTrue(v["name"] and v["guru"] and v["ask"] and v["how"])


class TestMemoGate(unittest.TestCase):
    """위원회 메모 관문 — gate.from_date(2026-11-22) 이후 메모부터 구루 교차 점검을 요구한다"""
    BASE = {"id": "us-xyz", "date": "2026-11-15", "verdict": "focus", "thesis": "t", "edge_type": "analytical", "other_side": "지수 매도",
            "evidence": ["https://a", "https://b"], "consensus_gap": [{"driver": "FY27 매출", "ours": 120, "consensus": 100, "source": "Fiscal.ai"}],
            "price": 10, "scenarios": {"bull": {"value": 20, "p": 0.3}, "base": {"value": 13, "p": 0.5}, "bear": {"value": 7, "p": 0.2}},
            "catalysts": [{"date": "2027-01-10", "what": "실적"}], "premortem": ["a", "b", "c"],
            "kills": [{"metric": "m", "threshold": "t", "deadline": "d", "source": "s"}, {"metric": "m2", "threshold": "t", "deadline": "d", "source": "s"}],
            "implied": {"growth": 0.1, "pctile": 60, "source": "역DCF"}, "red_team": {"verdict": "유지", "answered": True}, "expiry": "2027-11-14"}

    def test_old_memo_unaffected(self):
        ok, fails, _, nums = memo_check.check(copy.deepcopy(self.BASE))
        self.assertTrue(ok, fails)
        self.assertNotIn("playbook", nums)

    def test_new_memo_needs_playbook(self):
        ok, fails, _, _ = memo_check.check(dict(copy.deepcopy(self.BASE), date=CFG["gate"]["from_date"]))
        self.assertFalse(ok)
        self.assertTrue(any(f.startswith("구루 교차 점검") for f in fails))

    def test_new_memo_passes_with_playbook(self):
        ok, fails, _, nums = memo_check.check(dict(copy.deepcopy(self.BASE), date=CFG["gate"]["from_date"], playbook=good_pb()))
        self.assertTrue(ok, fails)
        self.assertEqual(nums["playbook"]["pass"], 4)

    def test_block_present_is_checked_even_before_date(self):
        bad = good_pb()
        bad["hold"] = {}
        ok, fails, _, _ = memo_check.check(dict(copy.deepcopy(self.BASE), playbook=bad))
        self.assertFalse(ok)
        self.assertTrue(any("보유 규율" in f for f in fails))

    def test_hold_records_only(self):
        ok, fails, _, _ = memo_check.check(dict(copy.deepcopy(self.BASE), date=CFG["gate"]["from_date"], verdict="hold"))
        self.assertTrue(ok)
        self.assertTrue(any(f.startswith("구루 교차 점검") for f in fails))


class TestDrawdowns(unittest.TestCase):
    def test_review_list_not_exclusion(self):
        rows = [{"ticker": "AAA", "status": "추적", "kill_conditions": "수주잔고 2분기 연속 감소"},
                {"ticker": "BBB", "status": "종료"}, {"ticker": "CCC", "status": "관찰"},
                {"ticker": "DDD", "status": "추적"}, {"ticker": "EEE", "status": "추적"}, {"ticker": "aaa", "status": "추적"}]
        book = {"us-aaa": (-0.62, -0.70, 300), "x-bbb": (-0.90, -0.90, 300), "us-ccc": (-0.20, -0.30, 300),
                "us-ddd": (None, None, 0), "x-eee": (-0.75, -0.80, 300)}
        out = pb.drawdowns(CFG, rows=rows, dd=lambda e: book[e], ids={"BBB": "x-bbb", "EEE": "x-eee"})
        self.assertEqual([r["ticker"] for r in out], ["EEE", "AAA"])   # 깊은 순, 종료·자료 없음·얕은 낙폭은 빠진다, 같은 종목은 한 번
        self.assertIn("제외 사유가 아니다", out[0]["note"])
        self.assertEqual(out[1]["kills"], "수주잔고 2분기 연속 감소")

    def test_drawdown_from_ohlcv(self):
        saved = pb.CO
        try:
            pb.CO = Path(tempfile.mkdtemp())
            (pb.CO / "us-up").mkdir()
            closes = [50 + 2 * i for i in range(26)] + [80, 60, 50, 40]       # 고점 100 → 40
            rows = ["date,open,high,low,close,volume"] + [f"2026-01-{i + 1:02d},1,1,1,{c},10" for i, c in enumerate(closes)]
            (pb.CO / "us-up" / "ohlcv.csv").write_text("\n".join(rows), encoding="utf-8")
            now, mdd, n = pb.drawdown("us-up")
            self.assertEqual((now, mdd, n), (-0.6, -0.6, 30))
            (pb.CO / "us-few").mkdir()
            (pb.CO / "us-few" / "ohlcv.csv").write_text("\n".join(rows[:10]), encoding="utf-8")
            self.assertEqual(pb.drawdown("us-few"), (None, None, 9))            # 봉이 모자라면 미확인
            self.assertEqual(pb.drawdown("us-none"), (None, None, 0))
        finally:
            pb.CO = saved


class TestScorecardTail(unittest.TestCase):
    def test_long_horizons(self):
        self.assertIn(730, leads.HORIZONS)
        self.assertIn(1095, leads.HORIZONS)

    def test_tail_metrics(self):
        ex = [-0.5, -0.2, -0.1, 0.0, 0.1, 0.1, 0.2, 0.3, 0.5, 3.0]
        rets = [-0.4, -0.1, 0.0, 0.1, 0.2, 0.2, 0.3, 0.4, 0.6, 3.2]
        t = leads.tail(ex, rets)
        self.assertEqual(t["p90_excess"], 0.5)
        self.assertEqual(t["tail_2x"], 0.1)            # 10개 중 1개가 2배 이상
        self.assertEqual(t["top10_share"], 0.714)      # 상위 1개가 양(+)의 초과 4.2 중 3.0

    def test_tail_edges(self):
        self.assertEqual(leads.tail([], []), {})
        self.assertIsNone(leads.tail([-0.2, -0.1], [-0.2, -0.1])["top10_share"])


class TestWording(unittest.TestCase):
    """마스터 지시(2026-11-19) — 산출물·지시서에 '테제'를 쓰지 않는다"""
    def test_no_banned_word_in_new_files(self):
        for rel in ("knowledge/methods/tenbagger_playbook.md", "config/tenbagger_playbook.yaml", "scripts/tenbagger/playbook.py"):
            self.assertNotIn("테제", (ROOT / rel).read_text(encoding="utf-8"), rel)


if __name__ == "__main__":
    unittest.main()
