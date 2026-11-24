"""Consumer Trends 판매 채널 층(radar/consumer_market.py) 오프라인 시험 — 2026-11-24 마스터 지시"""
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import consumer_market as cm  # noqa: E402


class T(unittest.TestCase):
    def test_brand_match(self):
        bm = cm.brand_map()
        self.assertEqual(cm.match("HOKA Clifton 9 running shoe", bm)["ticker"], "DECK")
        self.assertIsNone(cm.match("Generic lamp", bm))

    def test_keys_pending(self):
        r, w = cm.junglescout({}, {})
        self.assertIsNone(r)
        self.assertIn("키 대기", w)
        r, w = cm.fastmoss({}, {})
        self.assertIn("키 대기", w)

    def test_fastmoss_parse_and_key_header(self):
        resp = {"code": 0, "data": {"list": [{"product_id": "1", "title": "Labubu blind box", "shop": {"name": "POP MART"}, "gmv": 10, "units_sold": 2, "growth_rate": 1.5}]}}
        with mock.patch.object(cm, "post", return_value=resp) as p:
            rows, _ = cm.fastmoss({"regions": ["US"]}, {"FASTMOSS_API_KEY": "sek"})
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(p.call_args[0][2]["Authorization"], "Bearer sek")

    def test_junglescout_header(self):
        with mock.patch.object(cm, "post", return_value={"data": [{"id": "us/B1", "attributes": {"title": "x", "brand": "Crocs"}}]}) as p:
            rows, _ = cm.junglescout({"queries": [{"marketplace": "us", "categories": ["Shoes"]}]}, {"JUNGLESCOUT_KEY_NAME": "n", "JUNGLESCOUT_API_KEY": "k"})
        self.assertEqual(p.call_args[0][2]["Authorization"], "n:k")
        self.assertEqual(rows[0]["id"], "us/B1")

    def test_post_error_hides_key(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("Bearer sek")):
            with self.assertRaises(RuntimeError) as c:
                cm.post("https://x", {}, {"Authorization": "Bearer sek"})
        self.assertNotIn("sek", str(c.exception))


if __name__ == "__main__":
    unittest.main()
