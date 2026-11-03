"""매수 위치(일봉) (마스터 지시 2026-11-03)"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import entry_view as ev  # noqa: E402


def bars(n=260):
    out = []
    for i in range(n):
        c = 100 + 0.1 * i + 8 * math.sin(i / 12)
        out.append({"date": f"d{i:03d}", "o": c, "h": c * 1.01, "l": c * 0.99, "c": c, "v": 1e6})
    return out


class TestEntry(unittest.TestCase):
    def test_lower_entry_has_more_upside(self):
        lv = ev.daily_levels(bars())
        rows = ev.ladder(lv, lv["price"] * 1.3)
        self.assertAlmostEqual(rows[0]["up_target"], 0.3, places=6)
        for r in rows[1:]:
            self.assertLess(r["price"], lv["price"])
            self.assertGreater(r["up_target"], rows[0]["up_target"])

    def test_section_and_short_history(self):
        s = ev.section(bars(), 150)
        self.assertEqual(s["h2"], "매수 위치(일봉)")
        self.assertIsNone(ev.section(bars(100), 150))


if __name__ == "__main__":
    unittest.main()
