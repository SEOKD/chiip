"""애플 평점 수 원천(radar/consumer_attention.py ratings) 오프라인 시험 — 2026-11-12 마스터 지시"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import consumer_attention as ca  # noqa: E402


class TestRatings(unittest.TestCase):
    def test_artist_id(self):
        self.assertEqual(ca._artist_id({"artistUrl": "https://apps.apple.com/us/developer/duolingo/id570060151?uo=2"}), "570060151")
        self.assertEqual(ca._artist_id({"artistId": 42}), "42")
        self.assertIsNone(ca._artist_id({}))

    def test_sum_and_spike(self):
        orig = ca._get_json
        ca._get_json = lambda *a, **k: {"results": [{"wrapperType": "artist"}, {"wrapperType": "software", "userRatingCount": 10},
                                                    {"wrapperType": "software", "userRatingCount": 5}]}
        try:
            self.assertEqual(ca.apple_ratings(["1"], "us", "ua"), (15, 2))
        finally:
            ca._get_json = orig
        latest = {"x": {"name": "X", "wiki": {}, "steam": {}, "news": {}, "ratings": {"us": {"accel": 3.0, "gain7": 5000}, "jp": {"accel": 3.0, "gain7": 10}}}}
        sp = ca.spikes(latest, 2.0, 20000)
        self.assertEqual([(s["source"], s["key"]) for s in sp], [("apple_ratings", "us")])   # 1,000건 미만 증가는 잡음
        self.assertEqual(ca.demand_accel(latest["x"]), 3.0)


if __name__ == "__main__":
    unittest.main()
