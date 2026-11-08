"""산업 리포트 고도화 — 세그먼트 귀속·IB 논리 관문 (마스터 지시 2026-11-08, ADR-020)"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "industry"))
sys.path.insert(0, str(ROOT / "radar"))
import industry_segments as S  # noqa: E402
import logic as LG  # noqa: E402

GOOD = {"date": "2026-11-15", "narrative": {"status": "조건부 판단"}, "coverage": [{"name": "Micron", "country": "US"}, {"name": "SK하이닉스", "country": "KR"}], "logic": {
    "bottom_line": {"call": "한 문장 결론", "changed": "무엇이 바뀌었나", "vs_prior": "첫 판단"},
    "debates": [{"q": f"논쟁 {i}", "consensus": {"view": "시장", "source": "Fiscal.ai"}, "chiip": {"view": "Chiip"}, "why_differ": "이유",
                 "signpost": {"date": "2026-12-01", "metric": "지표", "threshold": "문턱"}, "p": 0.6} for i in range(3)],
    "drivers": [{"pool": "nand-flash", "ref": "nand-flash:co-micron", "name": "Micron NAND", "volume": {"name": "비트", "chg": 0.10}, "price": {"name": "ASP", "chg": 0.30}}],
    "expectations": [{"what": "컨센서스", "value": "+14%", "source": "Fiscal.ai"}],
    "scenarios": [{"case": c, "p": p, "assume": "가정", "kpi": "성장률(%)", "value": v} for c, p, v in (("약세", 0.25, 2), ("기본", 0.5, 15), ("강세", 0.25, 30))],
    "cycle": [{"name": n, "kind": k, "now": "1", "read": "읽기"} for n, k in (("a", "선행"), ("b", "동행"), ("c", "후행"))],
    "profit_pool": [{"layer": "칩", "before": "45%", "after": "87%", "why": "가격"}],
    "chain": [{"step": "사실", "type": "확정사실"}, {"step": "가이던스", "type": "가이던스"}, {"step": "추정", "type": "추정"}, {"step": "추론", "type": "자체추론"}]}}


class TestLogicGate(unittest.TestCase):
    def test_good_passes(self):
        self.assertEqual(LG.gate(GOOD, "quarterly"), [])

    def test_missing_pieces_named(self):
        dp = json.loads(json.dumps(GOOD))
        dp["logic"]["debates"] = dp["logic"]["debates"][:1]
        dp["logic"]["scenarios"][0]["p"] = 0.5
        dp["logic"]["expectations"] = []
        bad = " ".join(LG.gate(dp, "quarterly"))
        self.assertIn("핵심 논쟁 1개", bad)
        self.assertIn("확률 합", bad)
        self.assertIn("가격 내포 기대", bad)

    def test_unconfirmed_link_blocks_final_status(self):
        dp = json.loads(json.dumps(GOOD))
        dp["logic"]["chain"].append({"step": "모름", "type": "미확인"})
        dp["narrative"]["status"] = "판단 가능 — 다 확인됨"
        self.assertTrue(any("미확인 고리" in b for b in LG.gate(dp, "quarterly")))

    def test_banned_trading_words(self):
        dp = json.loads(json.dumps(GOOD))
        dp["narrative"]["view"] = "비중 확대가 맞다"
        self.assertTrue(any("금지 표현" in b for b in LG.gate(dp, "weekly")))

    def test_single_country_blocked(self):
        dp = json.loads(json.dumps(GOOD))
        dp["coverage"] = [{"name": "a", "country": "US"}, {"name": "b", "country": "US"}]
        dp["title"] = "한국 반도체 주간"
        bad = " ".join(LG.gate(dp, "weekly"))
        self.assertIn("나라 1곳", bad)
        self.assertIn("한 나라로 한정", bad)

    def test_weekly_needs_market_size_and_comps(self):
        bad = " ".join(LG.gate(GOOD, "weekly"))
        self.assertIn("시장 규모", bad)
        self.assertIn("비교 기업", bad)
        dp = json.loads(json.dumps(GOOD))
        dp["emerging"] = True
        self.assertTrue(any("로드맵" in b for b in LG.gate(dp, "quarterly")))

    def test_old_reports_exempt(self):
        self.assertEqual(LG.gate({"date": "2026-11-08"}, "event"), [])

    def test_bridge_residual_flags(self):
        b = LG.bridge(GOOD["logic"]["drivers"], {"nand-flash:co-micron": 0.20})
        self.assertAlmostEqual(b[0]["implied"], 0.43, places=4)
        self.assertAlmostEqual(b[0]["resid"], -0.23, places=4)
        rows = LG.sections(GOOD, "quarterly", {"nand-flash:co-micron": 0.20})["drivers"][0]["rows"]
        self.assertIn("잔차", rows[0][6])


class TestSegments(unittest.TestCase):
    def setUp(self):
        self._b = S.BASE
        S.BASE = Path(tempfile.mkdtemp())

    def tearDown(self):
        S.BASE = self._b

    def test_calendarization(self):
        self.assertEqual(S.cal_quarter("2026-10-02"), "2026Q3")   # 7~9월이 든 회계 분기
        self.assertEqual(S.cal_quarter("2026-09-03"), "2026Q3")
        self.assertEqual(S.cal_quarter("2026-12-31"), "2026Q4")

    def test_put_validates_and_aggregates_segment_only(self):
        f = S.BASE / "s.json"
        f.write_text(json.dumps([
            {"pool": "nand-flash", "id": "co-micron", "period_end": "2026-09-03", "currency": "USD", "seg_rev": 14.1e9, "seg_rev_prev_q": 9.9e9, "company_rev": 54.2e9, "grade": "A", "source": "10-K"},
            {"pool": "nand-flash", "id": "co-samsung", "period_end": "2026-09-30", "currency": "KRW", "company_rev": 195e12, "grade": "U", "method": "미공시"}]), encoding="utf-8")
        self.assertEqual(S.put("2026Q3", f), 2)
        rs = {r["id"]: r for r in S.rows("2026Q3", "nand-storage", {"USD": 1.0, "KRW": 0.00072})}
        self.assertEqual(rs["co-micron"]["exposure"], "부분 겸업")   # NAND 26% — 회사 전체를 NAND로 세지 않는다
        self.assertFalse(rs["co-samsung"]["aggregate"])            # 미공시는 합산 제외
        summ = S.pool_summary(list(rs.values()))
        self.assertAlmostEqual(summ["nand-flash"]["usd"], 14.1e9)
        self.assertEqual(summ["nand-flash"]["ab_share"], 1.0)

    def test_rejects_segment_bigger_than_company_and_wrong_quarter(self):
        f = S.BASE / "bad.json"
        f.write_text(json.dumps([{"pool": "hdd", "id": "co-wdc", "period_end": "2026-12-31", "currency": "USD", "seg_rev": 5e9, "company_rev": 4e9, "grade": "A", "source": "x"}]), encoding="utf-8")
        with self.assertRaises(SystemExit) as e:
            S.put("2026Q3", f)
        self.assertIn("회사 전체보다 크다", str(e.exception))
        self.assertIn("2026Q4", str(e.exception))

    def test_estimate_needs_method(self):
        self.assertTrue(any("브리지" in b for b in S.validate({"id": "x", "quarter": "2026Q3", "grade": "E", "seg_rev": 1, "source": "s"}, S.cfg())))


if __name__ == "__main__":
    unittest.main()
