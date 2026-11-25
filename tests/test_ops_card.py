"""Portfolio 운용 카드(마스터 지시 2026-11-25 '리셋 + 본격적인 포트폴리오 매니지먼트') 오프라인 시험"""
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "portfolio"))
import ops_card as O  # noqa: E402

D0 = date(2026, 11, 25)
NODD = lambda e: (-0.6 if e == "co-a" else None, None, 0)   # noqa: E731


def ctx(**kw):
    base = {"holdings": [{"id": "co-a", "ticker": "AAA", "status": "보유", "thesis": "현장 발전", "kpis": ["수주잔고"], "kills": ["잔고 감소"]},
                         {"id": "co-b", "ticker": "BBB", "status": "관심", "added_by": "chiip"}],
            "events": [{"date": "2026-12-07", "ticker": "AAA", "what": "IPO 보호예수 해제(424B4 …)"}, {"date": "2026-11-01", "ticker": "AAA", "what": "지난 일"}],
            "watch": {"BBB": {"thesis_1line": "기판 병목", "kill_conditions": "점유율 하락; 증설 지연"}},
            "calls": {"co-a": {"date": "2026-11-14", "grade_now": "Buy", "target": 12.0, "price_now": 9.0, "bear": 7.0, "bull": 16.0},
                      "co-b": {"date": "2026-07-01", "grade_now": "Neutral", "target": 20.0, "price_now": 15.0, "bear": 16.0}},
            "book": {}, "review": {}, "killed": set(), "earn": [{"ticker": "AAA", "date": "2027-03-10"}]}
    base.update(kw)
    return base


class TestCard(unittest.TestCase):
    def test_holding_card_and_state(self):
        out = O.run(D0, ctx(), NODD, write=False)
        a, b = out["cards"]
        self.assertEqual((a["ticker"], a["state"]), ("AAA", "유지"))            # 보유가 먼저
        self.assertAlmostEqual(a["to_target"], 12 / 9 - 1)
        self.assertEqual([e["date"] for e in a["next"]], ["2026-12-07", "2027-03-10"])   # 지난 일은 빼고 가까운 순
        self.assertEqual(a["next"][0]["what"], "IPO 보호예수 해제")
        self.assertEqual(b["thesis"], "기판 병목")                                   # 카드가 없으면 텐배거 장부에서
        self.assertEqual(b["kills"], ["점유율 하락", "증설 지연"])
        self.assertEqual(b["state"], "경고")
        self.assertTrue(any("약세 시나리오" in w for w in b["why"]))                   # 현재가 < 약세
        self.assertTrue(any("리포트 147일 전" in w for w in b["why"]))
        self.assertTrue(any("지표 없음" in w for w in b["why"]))

    def test_broken_by_kill_or_book(self):
        out = O.run(D0, ctx(killed={"co-a"}), NODD, write=False)
        self.assertEqual(out["cards"][0]["state"], "훼손")
        out = O.run(D0, ctx(book={"co-a": {"verdict": "재점검", "reason": "보유 · 알파 4.6 < 6.0"}}), NODD, write=False)
        self.assertEqual(out["cards"][0]["state"], "경고")

    def test_daily_and_table(self):
        out = O.run(D0, ctx(), NODD, write=False)
        d = O.daily(out).splitlines()
        self.assertEqual(d[0], "AAA 투자 논리 유지 — 볼 지표: 수주잔고 · 다음 12/07 IPO 보호예수 해제")
        self.assertTrue(d[1].startswith("BBB 투자 논리 경고 — "))
        t = O.table(out)
        self.assertIn("| AAA | 보유 | 유지 |", t)
        self.assertIn("섹터 집중도", t)
        self.assertIn("매매·비중·금액 지시가 아니다", t)
        for bad in ("사라", "팔아라", "매수하라", "매도하라", "비중 확대", "비중 축소"):
            self.assertNotIn(bad, t + "\n".join(d))

    def test_watch_count_vs_target(self):
        out = O.run(D0, ctx(), NODD, write=False)
        self.assertEqual(out["watch"]["n"], 1)
        self.assertTrue(out["watch"]["short"])                                       # 목표 8개보다 적다
        self.assertIn("관심 종목 1개", O.daily(out))

    def test_live_config_holdings_have_cards(self):
        """리셋 뒤 보유 EROC·INIO에 운용 카드(thesis·kpis·kills)가 있어야 한다"""
        import yaml
        hs = [h for h in yaml.safe_load((ROOT / "config" / "portfolio.yaml").read_text(encoding="utf-8"))["holdings"] if h.get("status") == "보유"]
        self.assertEqual(sorted(h["ticker"] for h in hs), ["EROC", "INIO"])
        for h in hs:
            self.assertTrue(h.get("thesis") and len(h.get("kpis") or []) >= 2 and len(h.get("kills") or []) >= 2, h["ticker"])


if __name__ == "__main__":
    unittest.main()
