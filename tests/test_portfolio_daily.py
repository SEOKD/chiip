"""Portfolio Daily 섹터 동적 선정·서술형 양식 검사 시험 (마스터 지시 2026-11-13, ADR-023)"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "portfolio"))
import daily_check as dc  # noqa: E402
import sector_select as ss  # noqa: E402

C = {"weights": {"momentum": 0.40, "flow": 0.35, "alpha": 0.25}, "enter": {"score": 6.5, "pillars": 2}, "exit": {"score": 4.5, "pillars": 1},
     "confirm_runs": 2, "max_sectors": 8, "min_members": 3, "protect_status": ["보유"], "near_high": 0.97, "eps_rev_days": 20,
     "pillar_on": {"momentum": {"pct": 0.70, "rs20_min": 0.0}, "flow": {"pct": 0.70, "turnover_min": 1.15, "r5_min": 0.0}, "alpha": {"n_ge5": 2, "max_ge": 7.0}},
     "bootstrap_active": ["a"]}


def g(*mem):
    return {"name": mem[0], "etf": None, "members": list(mem), "chiip": False}


def mx(score, pillars, name="x"):
    return {"name": name, "score": score, "pillars": pillars, "r5": 0.01, "r20": 0.02, "rs5": 0.01, "rs20": 0.03, "near_high": 1, "n": 4,
            "turnover": 1.3, "relvol": 1.1, "eps_rev": None, "alpha_n5": 0, "alpha_max": None}


class SectorSelect(unittest.TestCase):
    def setUp(self):
        self.gs = {"a": g("A1", "A2", "A3"), "b": g("B1", "B2", "B3"), "c": g("C1", "C2", "C3")}

    def test_enter_needs_two_distinct_days(self):
        m = {"a": mx(5, ["알파"]), "b": mx(7.5, ["모멘텀", "수급"])}
        rows, st = ss.decide(m, {}, "2026-11-12", C, {}, self.gs)
        self.assertEqual({r["id"]: r["tag"] for r in rows}["b"], "편입 후보")
        rows, st = ss.decide(m, st, "2026-11-12", C, {}, self.gs)          # 같은 날 다시 돌려도 횟수가 늘지 않는다
        self.assertEqual({r["id"]: r["tag"] for r in rows}["b"], "편입 후보")
        rows, st = ss.decide(m, st, "2026-11-13", C, {}, self.gs)
        self.assertEqual({r["id"]: r["tag"] for r in rows}["b"], "신규 편입")
        self.assertIn("b", st["active"])

    def test_single_pillar_never_enters(self):
        m = {"a": mx(5, ["알파"]), "b": mx(9.0, ["모멘텀"])}
        st = {}
        for d in ("2026-11-12", "2026-11-13", "2026-11-14"):
            rows, st = ss.decide(m, st, d, C, {}, self.gs)
        self.assertNotIn("b", st["active"])

    def test_exit_warns_then_drops_but_protected_stays(self):
        st = {"active": {"a": {}, "b": {}}, "dates": ["2026-11-11"], "streak": {}}
        weak = {"a": mx(3.0, []), "b": mx(3.0, [])}
        rows, st = ss.decide(weak, st, "2026-11-12", C, {"a": ["EROC"]}, self.gs)
        tags = {r["id"]: r["tag"] for r in rows}
        self.assertEqual(tags, {"a": "약세 지속", "b": "제외 예정"})
        rows, st = ss.decide(weak, st, "2026-11-13", C, {"a": ["EROC"]}, self.gs)
        tags = {r["id"]: r["tag"] for r in rows}
        self.assertEqual(tags["b"], "제외")
        self.assertEqual(tags["a"], "약세 지속")
        self.assertNotIn("b", st["active"])
        self.assertIn("a", st["active"])

    def test_hysteresis_band_keeps(self):
        st = {"active": {"b": {}}, "dates": ["2026-11-11"], "streak": {}}
        rows, st = ss.decide({"b": mx(5.0, ["모멘텀"])}, st, "2026-11-12", C, {}, self.gs)    # 편입 문턱 아래지만 꺾임 문턱 위
        self.assertEqual(rows[0]["tag"], "유지")

    def test_cap_keeps_protected_first(self):
        gs = {f"s{i}": g(f"S{i}a", f"S{i}b", f"S{i}c") for i in range(10)}
        st = {"active": {k: {} for k in gs}, "dates": ["2026-11-11"], "streak": {}}
        m = {k: mx(6.0 - i * 0.1, ["모멘텀"]) for i, k in enumerate(gs)}
        rows, st = ss.decide(m, st, "2026-11-12", {**C, "max_sectors": 8}, {"s9": ["EROC"]}, gs)
        kept = [r["id"] for r in rows if r["tag"] in ("유지", "약세 지속", "신규 편입", "제외 예정")]
        self.assertEqual(len(kept), 8)
        self.assertIn("s9", kept)                       # 점수는 꼴찌지만 보유 섹터

    def test_duplicate_theme_not_added(self):
        gs = {"a": g("X1", "X2", "X3"), "b": g("X1", "X2", "Y3")}
        st = {"active": {"a": {}}, "dates": ["2026-11-11"], "streak": {}}
        m = {"a": mx(7, ["모멘텀", "수급"]), "b": mx(7, ["모멘텀", "수급"])}
        for d in ("2026-11-12", "2026-11-13"):
            rows, st = ss.decide(m, st, d, C, {}, gs)
        self.assertNotIn("b", st["active"])

    def test_bootstrap_uses_fixed_list(self):
        rows, st = ss.decide({"a": mx(3, [])}, {}, "2026-11-12", C, {}, self.gs)
        self.assertIn("a", st["active"])

    def test_alpha_missing_is_unknown_not_zero(self):
        q = {s: ss._row([10, 2, 5, 1.2, 130, 100, 10.2, None]) for s in ["A1", "A2", "A3", "B1", "B2", "B3", "SPY"]}
        m, _ = ss.metrics({"a": g("A1", "A2", "A3"), "b": g("B1", "B2", "B3")}, q, "SPY", {}, {}, {"A1": 6.0, "A2": 6.0}, C)
        ss.score(m, C)
        self.assertIsNone(m["b"]["alpha"])
        self.assertGreater(m["a"]["alpha"], 0)
        self.assertGreater(m["b"]["score"], 0)

    def test_reason_two_numbers_max(self):
        r = {"pillars": ["모멘텀", "수급", "알파"], "rs20": 0.042, "turnover": 1.31, "alpha_n5": 2, "alpha_max": 7.1}
        for s in dc.sentences(ss.reason(r, "신규 편입")):
            self.assertLessEqual(dc._measures(s), 2, s)

    def test_josa(self):
        self.assertEqual(ss._josa("방산·항공우주"), "는")
        self.assertEqual(ss._josa("필수소비재"), "는")
        self.assertEqual(ss._josa("미디어·엔터"), "는")
        self.assertEqual(ss._josa("금광"), "은")


GOOD = """[Chiip Portfolio Daily 11/13]

금리가 하루 만에 13bp 뛰면서 보유 종목 대부분이 밀렸습니다. 예외는 CBRS 하나로, 실적 발표 뒤 장후에 18% 가까이 올랐습니다.

■ 시장
미국 10년물 금리가 5.13%까지 올랐습니다. 일주일 사이 25bp 가까이 오른 셈입니다. S&P 500은 0.4% 내리는 데 그쳤지만, 먼 미래 이익에 기대는 성장주일수록 이런 금리 상승에 약합니다.

■ 섹터
AI 서버·네트워크 — 한 달 동안 주가는 24.5% 빠졌지만 이익 추정은 8.6% 올랐습니다.

■ 내 종목
CBRS(Cerebras)는 이번 분기 매출이 기대에 살짝 못 미쳤습니다. 하지만 다음 분기 매출 전망을 시장 예상보다 15~23% 높게 내놓았고, 장후 주가가 $97.75에서 $115로 뛰었습니다.

AXTI(AXT, 화합물 반도체 기판 회사)는 7.3% 내렸습니다.

■ 앞으로 챙길 것
11/17(화) 장 마감 뒤 NVDA 실적이 나옵니다.

■ 모델이 보는 위험(연구용 가상 지표)
모델이 보는 위험은 높습니다. 1년 변동성이 71% 수준입니다. 그래서 모델 기준 현금 비중은 93%입니다.

■ 확인 못 한 것
- CBRS 10-Q — 원문 미확인

1차 판정, 미검증 · 공개 자료 기반 분석이며 투자 권유가 아님
"""
POOL = {"t": [0.13, 0.178, 5.13, 0.25, -0.004, -0.245, 0.086, 15.4, 22.9, 97.75, 115.15, -7.3, 0.709, 0.928]}
FOLLOW = ["CBRS", "AXTI"]


class DailyCheck(unittest.TestCase):
    def setUp(self):
        self._pool, self._cov = dc.pool, dc.coverage_changed
        dc.pool = lambda day=None, extra=None: POOL
        dc.coverage_changed = lambda day: {"CBRS": (False, False), "AXTI": (True, False)}
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump({"moves": {"CBRS": 17.8, "AXTI": -7.3}}, self.tmp)
        self.tmp.close()

    def tearDown(self):
        dc.pool, dc.coverage_changed = self._pool, self._cov
        Path(self.tmp.name).unlink()

    def run_(self, text):
        return dc.check(text, "2026-11-13", Path(self.tmp.name), FOLLOW)[0]

    def test_master_examples_pass(self):
        self.assertEqual(self.run_(GOOD), [])

    def test_fabricated_number_caught(self):
        e = self.run_(GOOD.replace("5.13%까지", "5.31%까지"))
        self.assertTrue(any("5.31" in x for x in e), e)

    def test_labels_and_dot_chains(self):
        bad = GOOD.replace("AXTI(AXT, 화합물 반도체 기판 회사)는 7.3% 내렸습니다.", "- 판단: AXTI 약세\n- 무엇: 7.3% · 13bp · 5.13%")
        e = self.run_(bad)
        self.assertTrue(any("머릿말" in x for x in e))
        self.assertTrue(any("이어 붙이기" in x for x in e))

    def test_jargon(self):
        e = self.run_(GOOD.replace("1년 변동성이", "HRP 기준 변동성이"))
        self.assertTrue(any("HRP" in x for x in e))

    def test_explain_on_first_use(self):
        e = self.run_(GOOD.replace("NVDA 실적이 나옵니다.", "NVDA 실적이 나옵니다. INIO 오버행도 있습니다."))
        self.assertTrue(any("오버행" in x for x in e))
        self.assertEqual(self.run_(GOOD.replace("NVDA 실적이 나옵니다.", "NVDA 실적이 나옵니다. 물량이 풀리는 일정(오버행)도 있습니다.")), [])

    def test_count_mismatch(self):
        e = self.run_(GOOD.replace("보유 종목 대부분이", "보유 종목 11개 중 10개가"))
        self.assertTrue(any("종목 수 불일치" in x for x in e), e)

    def test_order_by_move(self):
        a = "CBRS(Cerebras)는 이번 분기 매출이 기대에 살짝 못 미쳤습니다. 하지만 다음 분기 매출 전망을 시장 예상보다 15~23% 높게 내놓았고, 장후 주가가 $97.75에서 $115로 뛰었습니다."
        b = "AXTI(AXT, 화합물 반도체 기판 회사)는 7.3% 내렸습니다."
        e = self.run_(GOOD.replace(a + "\n\n" + b, b + "\n\n" + a))
        self.assertTrue(any("등락 큰 순" in x for x in e), e)

    def test_target_only_when_changed(self):
        e = self.run_(GOOD.replace("장후 주가가", "목표가는 그대로였고 장후 주가가"))
        self.assertTrue(any("목표가" in x for x in e), e)

    def test_unverified_gathered(self):
        e = self.run_(GOOD.replace("7.3% 내렸습니다.", "7.3% 내렸습니다. 공시는 원문 미확인입니다."))
        self.assertTrue(any("원문 미확인" in x for x in e))

    def test_brief_section_and_order(self):
        e = self.run_(GOOD.replace("■ 앞으로 챙길 것", "■ 간단히\n짧게.\n\n■ 앞으로 챙길 것"))
        self.assertTrue(any("간단히" in x for x in e))
        e = self.run_(GOOD.replace("■ 시장", "■ 섹터X").replace("■ 섹터\n", "■ 시장\n").replace("■ 섹터X", "■ 섹터"))
        self.assertTrue(any("순서" in x for x in e), e)

    def test_monday_sections_have_slots(self):
        sec = "■ 섹터 배분(모델)\n이번 주 모델은 에너지 섹터를 가장 높게 봅니다.\n\n"
        ok = GOOD.replace("■ 내 종목", sec + "■ 내 종목")
        self.assertEqual(self.run_(ok), [])
        bad = GOOD.replace("■ 시장", sec + "■ 시장")
        self.assertTrue(any("섹터 배분" in x for x in self.run_(bad)))

    def test_paragraph_spacing(self):
        bad = GOOD.replace("■ 앞으로 챙길 것
11/17(화) 장 마감 뒤 NVDA 실적이 나옵니다.", "■ 앞으로 챙길 것
11/17(화) 장 마감 뒤 NVDA 실적이 나옵니다.
12/1 일정입니다.")
        self.assertTrue(any("빈 줄" in x for x in self.run_(bad)))

    def test_lead_limits_and_disclaimer(self):
        e = self.run_(GOOD.replace("1차 판정, 미검증 · 공개 자료 기반 분석이며 투자 권유가 아님", "끝"))
        self.assertTrue(any("면책" in x for x in e))

    def test_number_rules(self):
        self.assertEqual(dc._measures("하지만 다음 분기 매출 전망을 시장 예상보다 15~23% 높게 내놓았고, 장후 주가가 $97.75에서 $115로 뛰었습니다."), 2)
        self.assertEqual(dc._measures("S&P 500은 0.4% 내리는 데 그쳤지만, 10년물이 올랐습니다."), 1)
        self.assertEqual(dc._measures("11/17(화) 3분기 실적, 20일 동안"), 0)
        self.assertEqual(dc._measures("12/1 보호예수가 풀리는 물량이 발행 주식의 88.0%로, 하루 거래량의 90.6일치입니다."), 2)


if __name__ == "__main__":
    unittest.main()
