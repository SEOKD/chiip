"""포트폴리오 Mix·Mix 변화 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import narrative_view as nv  # noqa: E402


def quarters(pattern):
    return {"q": [{"period": f"{2023 + i // 4}-{(i % 4) * 3 + 3:02d}-28", "rev": 100 * (1 + 0.02 * i) * pattern[i % 4]} for i in range(12)]}


class T(unittest.TestCase):
    def test_seasonality(self):
        self.assertTrue(nv.seasonal({"quarters_hist": quarters([0.7, 1.0, 1.0, 1.4])}))
        self.assertFalse(nv.seasonal({"quarters_hist": quarters([1.0, 1.0, 1.0, 1.0])}))

    def test_mix_from_segments_qoq_when_not_seasonal(self):
        seg = {"A": [{"period": "2026-03-31", "rev": 60}, {"period": "2026-06-30", "rev": 70}],
               "B": [{"period": "2026-03-31", "rev": 40}, {"period": "2026-06-30", "rev": 30}]}
        dp = {"quarters_hist": quarters([1, 1, 1, 1]), "segments_hist": {"segments": seg},
              "narrative": {"lead": {"products": [{"name": "A"}, {"name": "B"}]}}}
        sec = nv.portfolio3(dp)
        rows = sec["blocks"][0]["rows"]
        self.assertEqual(rows[0][5:], ["70%", "+10.0%p"])
        self.assertIn("전 분기 대비", sec["blocks"][0]["headers"][-1])

    def test_model_supplied_shares(self):
        dp = {"quarters_hist": quarters([0.7, 1.0, 1.0, 1.4]),
              "narrative": {"lead": {"products": [{"name": "A", "rev_share": 0.55, "rev_share_prev": 0.5}]}}}
        rows = nv.portfolio3(dp)["blocks"][0]["rows"]
        self.assertEqual(rows[0][5:], ["55%", "+5.0%p"])


if __name__ == "__main__":
    unittest.main()
