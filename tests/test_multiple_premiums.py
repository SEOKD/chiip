"""반복 매출·수주 전환·가시성 멀티플 프리미엄 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
import multiples as m  # noqa: E402

CFG = yaml.safe_load((ROOT / "config" / "tenbagger.yaml").read_text(encoding="utf-8"))["multiple_select"]


class T(unittest.TestCase):
    def test_recurring_time_discount(self):
        now, _ = m.recurring_premium({"recurring": {"share": 0.6, "peer_share": 0.2, "years_to_recurring": 0}}, CFG)
        later, _ = m.recurring_premium({"recurring": {"share": 0.6, "peer_share": 0.2, "years_to_recurring": 3}}, CFG)
        self.assertAlmostEqual(later, now / 2, places=3)

    def test_recurring_below_peers_is_discount(self):
        v, _ = m.recurring_premium({"recurring": {"share": 0.05, "peer_share": 0.4}}, CFG)
        self.assertLess(v, 0)

    def test_retention_scales(self):
        hi, _ = m.recurring_premium({"recurring": {"share": 0.5, "peer_share": 0.2, "retention": 1.15}}, CFG)
        lo, _ = m.recurring_premium({"recurring": {"share": 0.5, "peer_share": 0.2, "retention": 0.9}}, CFG)
        self.assertGreater(hi, lo)

    def test_no_data_is_zero(self):
        self.assertEqual(m.recurring_premium({}, CFG)[0], 0.0)
        self.assertEqual(m.backlog_premium({}, CFG)[:2], (0.0, 0.0))

    def test_backlog_fast_and_visible(self):
        conv, vis, _ = m.backlog_premium({"backlog": {"conversion_months": 6, "coverage_next_fy": 1.0, "book_to_bill": 1.3, "rpo_12m_share": 0.8}}, CFG)
        self.assertAlmostEqual(conv, 0.04)
        self.assertAlmostEqual(vis, CFG["backlog"]["vis_cap"])
        slow, weak, _ = m.backlog_premium({"backlog": {"conversion_months": 24, "book_to_bill": 0.8, "cancel_rate": 0.1}}, CFG)
        self.assertLess(slow, 0)
        self.assertLess(weak, 0)

    def test_caps(self):
        v, _ = m.recurring_premium({"recurring": {"share": 1.0, "peer_share": 0.0, "retention": 1.3, "base_growth": 0.3}}, CFG)
        self.assertLessEqual(v, CFG["recurring"]["cap"])


if __name__ == "__main__":
    unittest.main()
