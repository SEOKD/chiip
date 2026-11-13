"""종목 범위 확대 1~4단계 연결 점검 (2026-11-13 아키텍처 점검) — 섹터 순환 후보가 알파 대상·리포트 순번·시세 관문까지 이어지는지"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in ("scripts/alpha", "scripts/tenbagger"):
    sys.path.insert(0, str(ROOT / p))
import pick_report  # noqa: E402
import score  # noqa: E402
import sector_shadow  # noqa: E402

ROT = {"sectors": {"Finance": {"name": "금융", "rows": [{"ticker": "PLMR", "name": "Palomar Holdings, Inc.", "symbol": "NASDAQ:PLMR"}]}}}


class Links(unittest.TestCase):
    def test_rotation_candidates_reach_alpha_and_report_universe(self):
        real = ROOT / "knowledge" / "models" / "discovery" / "rotation_candidates.json"
        if not real.exists():
            self.skipTest("순환 후보 없음")
        ids = set(score.rotation_names())
        self.assertTrue(ids)
        self.assertTrue(ids <= set(score.names()))
        uni = pick_report._universe()
        for i in ids:
            self.assertTrue(uni.get(i, {}).get("ticker"), i)

    def test_price_template_fills(self):
        tpl = (ROOT / "scripts" / "fiscal" / "templates" / "shadow_prices.js").read_text(encoding="utf-8")
        for k in ("__KEYS__", "__START__", "__MISSING__"):
            self.assertIn(k, tpl)

    def test_put_prices_accepts_wrapper(self):
        with tempfile.TemporaryDirectory() as d:
            f, out = Path(d) / "p.json", Path(d) / "store.json"
            f.write_text(json.dumps({"prices": {"SPY": [["2026-11-12", 757.1]]}, "errors": []}), encoding="utf-8")
            old = sector_shadow.PRICES
            sector_shadow.PRICES = out
            try:
                self.assertEqual(sector_shadow.put_prices(f), 1)
                self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["SPY"][0][1], 757.1)
            finally:
                sector_shadow.PRICES = old


if __name__ == "__main__":
    unittest.main()
