"""알파 감지 알림 — 기업 1줄·가정 줄 마지막·깨진 내러티브 머리 (마스터 지시 2026-11-08)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "valuation" / "v2"))
import alpha_watch as aw  # noqa: E402

R = {"entity": "co-ies", "drivers_as_of": "2026-11-08", "market": {"date": "2026-11-08"}, "coc": {"wacc": 0.101},
     "upside": {"implied_cagr": None, "n": 3000}}


class TestAlphaMessage(unittest.TestCase):
    def test_short_format_2026_11_13(self):   # 마스터 지시 2026-11-13 축약판
        r = dict(R, decision={"horizon": 5, "attractiveness": {"exp_return": 0.318, "margin_of_safety": 1.10}},
                 upside={"implied_cagr": -0.082, "implied_pct": (0, 74, ">500억$", "")})
        ref = {"item_id": "x:1", "title": "IES to Present at Conference", "url": "", "impact": None, "source_id": "src-pr"}
        reason = "보도자료: IES to Present at Conference"
        text = aw.message(r, "IES Holdings", 6.4, [reason, "알파 5.3 기준 진입"], refs={("co-ies", reason): ref}, use_model=False)
        L = text.split("\n")
        self.assertTrue(L[0].startswith("[알파 감지] IES Holdings — 알파 6.4"))
        self.assertTrue(L[1].startswith("☞"))
        i = L.index("왜 감지됐나")
        self.assertTrue(L[i + 1].startswith("· 보도자료:"))
        self.assertTrue(L[i + 2].strip().startswith("→"))
        self.assertIn("안전마진 9%", text)
        self.assertIn("연 기대수익 +31.8%", text)
        self.assertIn("100%가 이보다 높게 성장", text)
        self.assertNotIn("상위 100%", text)
        self.assertIn("최근 커버리지", text)
        for gone in ("요구수익률", "위험 예산", "상방(", "· 단계", "＋", "－", "확인할 것", "**", "투자자문 아님"):
            self.assertNotIn(gone, text)

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
        self.assertTrue(L[1].startswith("☞"))
        self.assertIn("왜 감지됐나", L)
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
