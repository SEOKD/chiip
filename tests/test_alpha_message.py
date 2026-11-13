"""알파 감지 알림 — 기업 1줄·가정 줄 마지막·깨진 내러티브 머리 (마스터 지시 2026-11-08)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "valuation" / "v2"))
import alpha_watch as aw  # noqa: E402

R = {"entity": "co-ies", "drivers_as_of": "2026-11-08", "market": {"date": "2026-11-08"}, "coc": {"wacc": 0.101},
     "upside": {"implied_cagr": None, "n": 3000}}


class TestAlphaMessage(unittest.TestCase):
    def test_bullet_format_2026_11_14(self):   # 마스터 지시 2026-11-14 머리표 양식(AAON 예시)
        r = dict(R, entity="us-aaon", decision={"horizon": 5, "attractiveness": {"exp_return": 0.088, "margin_of_safety": 0.45}},
                 upside={"implied_cagr": 0.15, "implied_pct": (54, 74, "", "")})
        ref = {"item_id": "x:1", "title": "8-K", "url": "", "impact": "11/10 대출계약 체결: $250M 텀론 추가 — 알파 변화 요인 아님", "source_id": "src-sec"}
        reason = "SEC 8-K 중요 계약: AAON, INC."
        L = aw.message(r, "AAON", 5.3, [reason], refs={("us-aaon", reason): ref}).split("\n")
        self.assertEqual(L[0], "[알파 감지] AAON — 알파 5.3")
        self.assertTrue(L[2].startswith("▶ 뭐하는 회사 : 상업용 공조"))
        self.assertNotIn("8-K", L[2])   # 출처 괄호는 뺀다
        self.assertIn("▶ 알파 감지 : 11/10 대출계약 체결. $250M 텀론 추가 — 알파 변화 요인 아님", L)
        text = "\n".join(L)
        for want in ("▶ 주가 전망 :", "* 연 기대수익 +8.8%", "* 주가 내포 5년 매출 성장 연 +15%", "* 안전마진 없음",
                     "* 비관적인 경우 가치가 시총의 45%", "▶ 내러티브 : ", "▶ 커버리지 : "):
            self.assertIn(want, text)
        for gone in ("왜 감지됐나", "☞", "요구수익률", "위험 예산", "상위 46%", "**", "투자자문 아님"):
            self.assertNotIn(gone, text)

    def test_multi_reason_bullets_and_mos(self):
        r = dict(R, decision={"horizon": 5, "attractiveness": {"exp_return": 0.318, "margin_of_safety": 1.10}})
        text = aw.message(r, "IES Holdings", 6.4, ["보도자료: IES to Present", "알파 5.3 기준 진입"])
        self.assertIn("▶ 알파 감지 :\n* 보도자료: IES to Present (본문 미확인 — 제목만)", text)
        self.assertIn("* 안전마진 9%", text)
        self.assertIn("* 비관적인 경우 가치가 시총의 1.10배", text)
        self.assertIn("역산 불가", text)

    def test_refresh_line_appended(self):
        text = aw.message(R, "IES Holdings", 6.4, ["알파 5.3 기준 진입"], refresh_note="리포트 갱신 대기열 등록 — 테스트")
        self.assertTrue(text.endswith("리포트 갱신 대기열 등록 — 테스트"))

    def test_counterparty_trace_not_own_item(self):   # 2026-11-13 AMAT 실적 자료가 SK하이닉스 '새 보도자료'로 감지됨
        it = {"source_id": "src-partner-trace", "trace_query": "osat-equip:co-skhynix", "doc_type": "보도자료",
              "title": "[협업 흔적] Q4 2026 Earnings Presentation - Applied Materials", "entities_matched": ["co-skhynix"]}
        self.assertFalse(aw.own_item(it))
        from datetime import datetime
        found, _ = aw.detect(datetime(2026, 11, 13, 7), {"alpha_seen": {"co-skhynix": 6.1}}, {"co-skhynix": 6.1}, {}, [],
                             {"lookback_hours": 26, "levels": ["P0", "P1"], "earnings_days_after": 1}, [it])
        self.assertNotIn("co-skhynix", found)

    def test_company_line_after_reasons_and_assumption_last(self):
        L = aw.message(R, "IES Holdings", 6.4, ["알파 5.3 기준 진입"], update_note="갱신").split("\n")
        self.assertTrue(L[2].startswith("▶ 뭐하는 회사"))
        self.assertNotIn("**", L)
        self.assertNotIn("투자자문 아님", L)
        self.assertFalse(any(x.startswith("가정:") for x in L))
        self.assertNotIn("보수 가정", "\n".join(L))

    def test_broken_front_still_reads(self):
        text = "---\nid: co-x\nas_of: 2026-11-08\nsummary: 'A + B'가 1순위 — 설명\nstage: 확산\nalpha_effect: {gap: +1, upside: 0}\n---\n본문"
        self.assertIsNotNone(aw.check_front(text))
        fm = aw.front(text)
        self.assertEqual(fm["stage"], "확산")
        self.assertIn("1순위", fm["summary"])
        self.assertEqual(fm["alpha_effect"]["gap"], 1)

    def test_good_front_passes_check(self):
        self.assertIsNone(aw.check_front('---\nid: co-x\nsummary: "‘A’가 1순위"\n---\n'))


if __name__ == "__main__":
    unittest.main()
