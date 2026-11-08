"""한국 전자기업 해외 거점 — 수출입 거울 신호·기사 소재 연결 (마스터 지시 2026-11-08)"""
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import overseas_sites as O  # noqa: E402


def months(n):
    out, y, m = [], 2024, 1
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


class TestSignals(unittest.TestCase):
    def test_yoy3(self):
        ms = months(24)
        s = {p: (200.0 if p >= "2025-10" else 100.0) for p in ms}
        g, v, last = O.yoy3(s)
        self.assertAlmostEqual(g, 1.0)
        self.assertEqual(last, "2025-12")

    def test_signal_threshold_and_owner(self):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE obs(reporter, flow, partner, hs, period, value, unit)")
        for p in months(24):
            db.execute("INSERT INTO obs VALUES('us','import','VN','851713',?,?,'USD')", (p, 4e8 if p >= "2025-10" else 2e8))
        c = {"min_usd_3m": 5e7, "surge_yoy": 0.3, "sites": [{"company": "co-samsung", "name": "삼성전자", "country": "VN", "place": "박닌", "items": [{"name": "스마트폰", "hs": "851713"}]}]}
        sig = O.signals(c, db)
        self.assertEqual(len(sig), 1)
        self.assertEqual(sig[0]["companies"], ["삼성전자"])
        self.assertIn("Census", sig[0]["source"])

    def test_config_sites_have_census_codes(self):
        c = O.cfg()
        self.assertTrue(all(s["country"] in c["census_country"] for s in c["sites"]))


if __name__ == "__main__":
    unittest.main()
