import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
import composite  # noqa: E402

STRONG = {"close": 100, "SMA50": 90, "SMA200": 80, "RSI": 60, "relative_volume_10d_calc": 1.5, "Perf.1M": 5, "Perf.3M": 10, "price_52_week_high": 105, "average_volume_30d_calc": 1000000}
TIMED = {"catalyst_days": 10, "new_primary": True, "revision_30d": 0.02, "sector_label": composite.TAILWIND}


class TestComposite(unittest.TestCase):
    def setUp(self):
        self.c = composite.cfg()
        self.alpha = {"total": 8.0, "components": {"asymmetry": 8.0}}

    def test_weights_and_parts_sum(self):
        self.assertAlmostEqual(sum(self.c["weights"].values()), 1.0)
        self.assertEqual(composite.technical(STRONG, self.c), 10)
        self.assertEqual(composite.timing(TIMED, self.c), 10)

    def test_all_strong_passes(self):
        x = composite.score({"ticker": "T", "name": "n", "tv": STRONG, "timing": TIMED}, self.alpha, self.c)
        self.assertEqual(x["composite"], 10.0)
        self.assertTrue(x["pass"])
        self.assertIn("종합 10.0/10", composite.line(x))

    def test_missing_timing_cannot_pass(self):
        x = composite.score({"ticker": "T", "tv": STRONG, "timing": {}}, self.alpha, self.c)
        self.assertEqual(x["composite"], 8.0)
        self.assertFalse(x["pass"])

    def test_gates(self):
        self.assertEqual(composite.score({"tv": STRONG, "timing": TIMED}, None, self.c)["why"], ["알파 미산정"])
        thin = {**STRONG, "average_volume_30d_calc": 10}
        self.assertIn("거래대금 미달", composite.score({"tv": thin, "timing": TIMED}, self.alpha, self.c)["why"])
        self.assertIn("킬 조건 발동", composite.score({"tv": STRONG, "timing": TIMED, "killed": True}, self.alpha, self.c)["why"])


class TestTextLint(unittest.TestCase):
    def test_lint(self):
        sys.path.insert(0, str(ROOT / "scripts" / "proviser"))
        import text_lint
        names = [r[1] for r in text_lint.lint("주가가 주가가 올랐다,, 그리고 끝.")]
        self.assertIn("같은 낱말 연속", names)
        self.assertIn("문장부호 중복", names)
        self.assertEqual(text_lint.lint("주가가 올랐다."), [])
        self.assertTrue(any("긴 문장" in r[1] for r in text_lint.lint("가" * 130)))


class TestPortfolioHyphen(unittest.TestCase):
    def test_company_line(self):
        sys.path.insert(0, str(ROOT / "radar"))
        import notify
        seen = {}
        orig = notify.brand
        notify.brand = lambda t: seen.setdefault("t", t)
        notify.guard = lambda t: "stop"
        try:
            notify.send("EROC ERock\n기업: 발전기", "PORTFOLIO")
        finally:
            notify.brand = orig
        self.assertIn("- 기업: 발전기", seen["t"])


if __name__ == "__main__":
    unittest.main()
