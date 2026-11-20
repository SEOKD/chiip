"""발표 뒤 Fiscal이 덮어쓴 칸을 발표 전 얼린 값으로 채운다 — ESE FY27 EBITDA 마진(2026-11-20)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "fiscal"))
import estimates as E  # noqa: E402


def row(m, v, saved="2026-11-12", rd="2027-09-30"):
    return {"saved": saved, "key": "NYSE_ESE", "report_date": rd, "period": "FY2027", "metric": m, "mean": str(v), "source": "agentic_consensus", "basis": "adjusted", "as_of": saved}


class Frozen(unittest.TestCase):
    def test_fill_margin_same_provider(self):
        out = {"key": "NYSE_ESE", "earningsDate": "2026-11-19", "fy_next_period": "2027-09-30",
               "pick": {"fy_next": {"revenue": None, "ebitda_adjusted": None, "ebitda_margin": None}}}
        stored = [row("revenue", 2020000000), row("ebitda_adjusted", 440000000), row("revenue", 2070000000, saved="2026-11-19")]
        n = E.fill_frozen(out, stored)
        p = out["pick"]["fy_next"]
        self.assertEqual(p["revenue"]["est"], 2020000000.0)   # 발표일(11-19) 저장분은 쓰지 않는다
        self.assertAlmostEqual(p["ebitda_margin"]["est"], 440 / 2020)
        self.assertEqual(n, 3)


if __name__ == "__main__":
    unittest.main()
