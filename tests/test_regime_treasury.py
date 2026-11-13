"""FRED가 막히면 미 재무부 국채 수익률로 우회(2026-11-14 파이프라인 점검)"""
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "valuation" / "v2"))
import regime  # noqa: E402

XML = ("<m:properties><d:NEW_DATE m:type=\"Edm.DateTime\">2026-11-12T00:00:00</d:NEW_DATE><d:BC_10YEAR m:type=\"Edm.Double\">5.10</d:BC_10YEAR>"
       "<d:BC_30YEAR m:type=\"Edm.Double\">5.43</d:BC_30YEAR></m:properties>")


class TestTreasuryFallback(unittest.TestCase):
    def test_fred_down_uses_treasury(self):
        def fred(sid, start):
            raise TimeoutError
        with mock.patch.object(regime.common, "http_get", lambda *a, **k: XML.encode()):
            reg = regime.build(fetch=fred, today=date(2026, 11, 14))
        self.assertAlmostEqual(reg["rf_us"], 0.051)
        self.assertEqual(reg["market"]["ust10y"]["route"], "우회(미 재무부)")
        self.assertTrue(any(e.startswith("DGS10") for e in reg["errors"]))   # 실패는 기록이 남는다


if __name__ == "__main__":
    unittest.main()
