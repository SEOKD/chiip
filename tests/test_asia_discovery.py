"""대만·중국·홍콩 발굴망 — 스크린 점수·이상치·업종 제외·A+H 중복, 중국·홍콩 공시 거르기, Pulse 분류(마스터 지시 2026-11-09)"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
sys.path.insert(0, str(ROOT / "radar"))
import asia_screen as A  # noqa: E402
from pollers import cn_hk_disclosure as D  # noqa: E402


def row(sym, desc, ind, mcap, g, om=10.0, ev=2.0, p6=0.0, vol=1e6, close=100.0):
    return {"symbol": sym, "name": sym.split(":")[1], "description": desc, "industry": ind, "market_cap_basic": mcap, "total_revenue_yoy_growth_ttm": g,
            "operating_margin_ttm": om, "enterprise_value_to_revenue_ttm": ev, "Perf.6M": p6, "average_volume_30d_calc": vol, "close": close}


class TestAsiaScore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.saved = (A.DIR, A.ASIA, A.ROOT, A.korea_links)
        A.DIR, A.ASIA, A.ROOT = t, t / "asia", t
        A.ASIA.mkdir()
        A.korea_links = lambda: ({}, [])
        self.c = json.loads(json.dumps(__import__("yaml").safe_load((ROOT / "config" / "asia_discovery.yaml").read_text(encoding="utf-8"))))

    def tearDown(self):
        A.DIR, A.ASIA, A.ROOT, A.korea_links = self.saved
        self.tmp.cleanup()

    def put(self, m, rows):
        (A.ASIA / f"{m}.json").write_text(json.dumps({"rows": rows}), encoding="utf-8")

    def test_outlier_exclusion_and_ah_dedupe(self):
        self.put("china", [row("SSE:603986", "Giga Device Semiconductor Inc. Class A", "Semiconductors", 1.9e11, 165, om=50),
                           row("SZSE:002379", "Shandong Hongqiao Aluminum Class A", "Metal Fabrication", 1.9e10, 9614),
                           row("SZSE:300313", "Xinjiang Tianshan Animal Husbandry Class A", "Agricultural Commodities/Milling", 2.4e9, 187),
                           row("SZSE:002289", "Shenzhen Success Electronics Co. Ltd. Class A", "Electronic Production Equipment", 8.9e9, 237)])
        self.put("hongkong", [row("HKEX:3986", "GigaDevice Semiconductor Inc. Class H", "Semiconductors", 2.2e11, 181),
                              row("HKEX:9976", "Shenzhen Longsys Electronics Co., Ltd. Class H", "Semiconductors", 1.0e11, 126),
                              row("HKEX:1626", "Jia Yao Holdings Limited", "Containers/Packaging", 1.7e10, 161)])
        res = A.score(self.c, tw={})
        cn = {r["code"]: r for r in res["china"]}
        self.assertNotIn("300313", cn)                       # 농업 업종 제외
        self.assertTrue(cn["002379"]["outlier"])             # +9,614%는 이상치
        self.assertIn("반도체·장비", cn["002289"]["themes"])
        hk = [r["code"] for r in res["hongkong"]]
        self.assertNotIn("3986", hk)                          # A주가 있는 H주는 뺀다
        self.assertNotIn("1626", hk)                          # 포장재 제외
        self.assertIn("9976", hk)

    def test_liquidity_floor(self):
        self.put("taiwan", [row("TPEX:9999", "Tiny Semi", "Semiconductors", 1.0e10, 300, vol=100, close=10)] +
                 [row(f"TWSE:{i}", f"Semi {i}", "Semiconductors", 2e10, 50 + i) for i in range(1000, 1004)])
        codes = [r["code"] for r in A.score(self.c, tw={"1001": {"accel": 40, "yoy": 90, "period": "2026-10"}})["taiwan"]]
        self.assertNotIn("9999", codes)                       # 거래대금 $2M 미만
        self.assertEqual(len(codes), 4)


class TestCnHkFilter(unittest.TestCase):
    def test_keep_skip(self):
        self.assertTrue(D.CN_KEEP.search("2026年第三季度报告"))
        self.assertTrue(D.CN_SKIP.search("H股公告-翌日披露报表"))
        self.assertTrue(D.HK_KEEP.search("ESTIMATED RESULTS FOR THE FIRST THREE QUARTERS OF 2026"))
        self.assertTrue(D.HK_SKIP.search("An announcement has just been published by the issuer in the Chinese section of this website"))
        self.assertTrue(D.HK_SKIP.search("POLL RESULTS OF THE EXTRAORDINARY SHAREHOLDERS' MEETING"))


class TestPulseClass(unittest.TestCase):
    def test_new_sources_classified(self):
        import pulse
        self.assertEqual(pulse.class_of("src-tw-revenue-surge"), "공시")
        self.assertEqual(pulse.class_of("src-cn-hk-disclosure"), "공시")
        self.assertTrue(pulse.relevant({"source_id": "src-cn-hk-disclosure", "title": "[China filing] 东芯股份(688110) 2026年第三季度报告"}, "공시"))


if __name__ == "__main__":
    unittest.main()
