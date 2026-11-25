"""코스피 시황은 Pulse로 보내지 않는다(2026-11-25 마스터 지시)"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import tg_channels as tg  # noqa: E402


class TestMarketWrap(unittest.TestCase):
    def test_wrap_skipped_company_news_kept(self):
        w = re.compile(tg.config()["skip_market_wrap"])
        self.assertTrue(w.search("코스피 −6.16% 마감, 삼성전자 −9.87%·SK하이닉스 −11.05%"))
        self.assertTrue(w.search("코스피 4,697.51, 코스닥 650.64(−2.29%). 외국인 순매도"))
        self.assertFalse(w.search("SK하이닉스, HBM4 공급계약 체결"))
        self.assertFalse(w.search("삼성전자 코스피 시총 1위 유지하며 HBM 증설"))

    def test_pulse_uses_filter(self):
        self.assertIn('cfg["skip_market_wrap"]', (ROOT / "radar" / "pulse.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
