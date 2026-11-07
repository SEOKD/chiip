"""커뮤니티 관심 급증 모델 시험 (마스터 지시 2026-11-07)"""
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import social_surge as s  # noqa: E402

KST = timezone(timedelta(hours=9))


def sig(day, src="twitter", i=0, hit=0.5, n=100, sent=0.5):
    return {"detectedAt": f"{day}T03:00:{i:02d}.000Z", "sourceType": src, "url": f"https://x.test/{day}/{src}/{i}",
            "sentimentScore": sent, "authorEvaluatedCalls": n, "authorHitRate": hit, "excerpt": "본문", "author": "누군가"}


class T(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        p = Path(self.d.name)
        self.patches = [mock.patch.object(s, "DIR", p), mock.patch.object(s, "DAILY", p / "daily.csv"), mock.patch.object(s, "SCORES", p / "scores.csv"),
                        mock.patch.object(s, "RECAPS", p / "recaps.csv"), mock.patch.object(s, "LATEST", p / "latest.json"), mock.patch.object(s, "STATE", p / "st.json"),
                        mock.patch.object(s, "id_map", lambda: {"ABC": "us-abc"})]
        for x in self.patches:
            x.start()

    def tearDown(self):
        for x in self.patches:
            x.stop()
        self.d.cleanup()

    def feed(self, per_day, end=date(2026, 11, 7), days=31):
        sigs = []
        for k in range(days):
            day = (end - timedelta(days=days - 1 - k)).isoformat()
            for i in range(per_day(k, days)):
                sigs.append(sig(day, i=i))
        s.put([{"ticker": "ABC", "signals": sigs}], now=datetime(2026, 11, 7, 12, tzinfo=KST))

    def test_no_text_or_author_stored(self):
        self.feed(lambda k, n: 1)
        txt = s.DAILY.read_text(encoding="utf-8")
        self.assertNotIn("본문", txt)
        self.assertNotIn("누군가", txt)
        self.assertNotIn("x.test", txt)

    def test_dedupe(self):
        self.feed(lambda k, n: 2)
        self.feed(lambda k, n: 2)
        rows = s._read(s.DAILY, s.DCOLS)
        self.assertEqual(sum(int(r["count"]) for r in rows), 62)

    def test_flat_is_quiet_and_spike_alerts(self):
        self.feed(lambda k, n: 2)
        r = s.compute(today=date(2026, 11, 7))["us-abc"]
        self.assertLess(abs(r["Z"]), 1.5)
        self.assertFalse(r["alert"])
        s.STATE.unlink()
        s.DAILY.unlink()
        self.feed(lambda k, n: 2 if k < n - 3 else 12)
        r = s.compute(today=date(2026, 11, 7))["us-abc"]
        self.assertGreater(r["Z"], 3)
        self.assertTrue(r["alert"])
        self.assertGreater(s.attention(r), 5)

    def test_credibility_weight_shrinks(self):
        prior = {"a": 9, "b": 11}
        self.assertAlmostEqual(s._weight({}, prior), 1.0)
        self.assertGreater(s._weight({"authorEvaluatedCalls": 300, "authorHitRate": 0.7}, prior), s._weight({"authorEvaluatedCalls": 3, "authorHitRate": 0.7}, prior))

    def test_poisson_and_ppf(self):
        self.assertAlmostEqual(s.pois_sf(0, 2), 1.0)
        self.assertAlmostEqual(s.pois_sf(1, 2), 1 - 2.718281828 ** -2, places=6)
        self.assertAlmostEqual(s.norm_ppf(0.975), 1.959964, places=4)


if __name__ == "__main__":
    unittest.main()
