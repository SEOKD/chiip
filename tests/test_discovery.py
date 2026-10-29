"""Chiip Ten-bagger Discovery 시험 (마스터 지시 2026-10-29 — 엣지 AI 밸류체인 종목 발굴·관심도·IB식 선별·원문 팔로업)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))

import attention  # noqa: E402
import promote  # noqa: E402
import screen  # noqa: E402
from pollers import tw_disclosure  # noqa: E402


class TestDiscovery(unittest.TestCase):
    def test_universe_has_master_examples(self):
        cands = attention.candidates()
        for cid in ("jp-taiyoyuden", "jp-jxmetals", "co-nittobo", "tw-yageo", "jp-uniontool"):
            self.assertIn(cid, cands)
        self.assertEqual(cands["tw-yageo"]["local"], "國巨")

    def test_screen_scores_and_gates(self):
        c = {"id": "x", "edge": 8}
        fund = {"x": {"rev_growth": 0.30, "n_analysts": 2, "mcap_usd": 1.5e9}}
        att = {"x": {"accel": 2.0, "crowding_pct": 20}}
        comp = screen.components(c, fund, att, {"x": 10.0}, {"min_usd": 1e8, "max_usd": 3e9})
        self.assertEqual(comp["coverage_gap"], 10.0)    # 애널리스트 3명 이하 = 커버리지 공백
        self.assertEqual(comp["size_fit"], 10.0)
        s, missing = screen.score(comp, {"edge": 0.3, "growth": 0.15, "coverage_gap": 0.1, "attention_accel": 0.15, "crowding": -0.1, "valuation": 0.15, "size_fit": 0.15})
        self.assertGreater(s, 6.0)
        self.assertEqual(missing, [])

    def test_attention_accel(self):
        rows = [("2026-10-01", "x", "news_global", "4"), ("2026-10-08", "x", "news_global", "4"), ("2026-10-15", "x", "news_global", "4"),
                ("2026-10-22", "x", "news_global", "4"), ("2026-10-29", "x", "news_global", "14")]
        out = attention.summarize(rows, "2026-10-29")
        self.assertAlmostEqual(out["x"]["accel"], 3.0)   # (14+1)/(4+1)

    def test_tw_disclosure_parsing_and_rules(self):
        self.assertEqual(tw_disclosure.roc_to_iso("1151028", "70003"), "2026-10-28T07:00:03+08:00")
        base = {"source_id": "src-tw-disclosure", "entities_matched": ["tw-emc"]}
        self.assertIsNotNone(promote.match({**base, "title": "台光電(2383) 重大訊息: 公告本公司及子公司董事會通過資本支出預算案"}))
        self.assertIsNone(promote.match({**base, "title": "台光電(2383) 重大訊息: 代子公司台光電子材料(昆山)股份有限公司公告 資金貸與達標準"}))
        self.assertTrue(attention.SELLSIDE_RE.search("台光電(2383) 重大訊息: 本公司受邀參加高盛證券舉辦之線上法人座談會"))


if __name__ == "__main__":
    unittest.main()
