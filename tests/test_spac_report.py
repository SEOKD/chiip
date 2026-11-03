"""SPAC 리포트 (마스터 지시 2026-11-03)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import report_html  # noqa: E402
import spac_report as sr  # noqa: E402

S = {"price": 9.29, "trust_per_share": 10.287, "status": "종결 전", "new_ticker": "AGLT", "redemption": {"shares": 25.45, "pct": 0.615},
     "cash": {"trust_left": 0.164, "pipe": 0.201, "other": 0.1, "fees": 0.05}, "shares": {"공개": 15.9, "스폰서": 10.4, "PIPE": 20.1, "기존": 196.0},
     "warrants": [{"name": "공개 워런트", "count": 4.1, "strike": 11.5}], "earnout": [{"holder": "기존", "shares": 15.0, "trigger": 15.0}],
     "fairness": {"low": 1.7, "base": 4.5, "high": 7.3}, "projections": [{"year": 2028, "rev": 0.3}], "peer_ev_rev": 8.0, "burn": 0.17}


class TestSpac(unittest.TestCase):
    def test_numbers(self):
        m = sr.compute(S)
        self.assertAlmostEqual(m["net_cash"], 0.415)
        self.assertAlmostEqual(m["basic"], 242.4)
        self.assertAlmostEqual(m["ev"], 9.29 * 242.4 / 1000 - 0.415)
        self.assertGreater(m["fully"], m["basic"])
        self.assertLess(m["trust_gap"], 0)

    def test_renders(self):
        m = sr.compute(S)
        d = {"format": 3, "title": "t", "date": "2026-11-03", "ticker": "CCXI", "company": "C", "biz": "b", "verdict": {"view": "v"},
             "tiles": sr.tiles(S, m), "sections": sr.sections(S, m), "sources": []}
        self.assertIn("합병 현금 다리", report_html.render(d))


if __name__ == "__main__":
    unittest.main()
