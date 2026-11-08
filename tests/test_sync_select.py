"""싱크로율 지표 자동 선택·다음 분기 모델 (마스터 지시 2026-11-08 — 제품 연관성 높은 PPI·수출입 세부 지표, 다음 분기 추산)"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import sync_view as V  # noqa: E402


def months(n, start=(2021, 1)):
    y, m = start
    for _ in range(n):
        yield f"{y}-{m:02d}"
        m += 1
        if m > 12:
            y, m = y + 1, 1


class TestSelect(unittest.TestCase):
    def setUp(self):
        self.db = Path(tempfile.mkdtemp()) / "hs.sqlite"
        c = sqlite3.connect(self.db)
        c.execute("CREATE TABLE obs (reporter, flow, partner, hs, period, value, unit)")
        ms = list(months(60))
        for i, m in enumerate(ms):   # 같은 품목(853400): 매출과 같은 방향으로 성장 / 다른 품목(853300)도 4자리 일치
            c.execute("INSERT INTO obs VALUES ('us','import','WORLD','853400',?,?, 'USD')", (m, 100 * 1.02 ** i * (1 + 0.05 * ((i // 3) % 2))))
            c.execute("INSERT INTO obs VALUES ('jp','export','WORLD','853490',?,?, 'JPY')", (m, 100 + (i % 7)))
        c.commit()
        c.close()
        qs = []
        for k, m in enumerate(ms[2::3]):
            qs.append({"period": f"{m}-28", "rev": 100 * 1.02 ** (3 * k + 2) * (1 + 0.05 * (k % 2)) * 1e6})
        self.dp = {"sync": {"products": [{"name": "인쇄회로기판", "hs": "853400", "share": 1.0}]}, "quarters_hist": {"q": list(reversed(qs))}}

    def test_candidates_from_product_hs(self):
        cs = V.candidates(self.dp, self.db)
        labels = [c[0]["label"] for c in cs]
        self.assertTrue(any("HS 853400" in x for x in labels))
        rel = {c[0]["hs"] if c[0]["source"] == "hs" else c[0]["input"]: c[1] for c in cs}
        self.assertEqual(rel["853400"], 1.0)        # 6자리 일치
        self.assertAlmostEqual(rel["853490"], 0.7)  # 4자리 일치
        self.assertTrue(any(c[0]["source"] == "ppi" and c[0]["input"] == "pcb" for c in cs))   # config inputs의 PCB PPI

    def test_negative_corr_scores_zero_for_own_product(self):
        row = {"ind": {"origin": "자동"}, "rel": 1.0, "rev": {"r": -0.9, "sig": True}}
        self.assertEqual(V.score(row), 0.0)
        row["ind"] = {"origin": "모델 지정"}
        self.assertAlmostEqual(V.score(row), 0.9)

    def test_chooses_matching_trade_series_and_models_next(self):
        c = V.compute(self.dp, history={"inputs": {}}, db=self.db)
        tr = [r for r in c["chosen"] if V.kind(r["ind"]) == "trade"]
        self.assertEqual(tr[0]["ind"]["hs"], "853400")
        self.assertIsNotNone(tr[0]["next"])

    def test_forecast_x_ar(self):
        iq = {V.shift_q("2020Q1", i): 100 * 1.03 ** i * (1 + 0.01 * ((i * 7) % 5 - 2)) for i in range(24)}
        x, se = V.forecast_x(iq, 4)
        self.assertLess(abs(x - (1.03 ** 4 - 1)), 0.05)   # 꾸준한 +3%/분기 지표 → 전년 대비 약 +12.6%
        self.assertIsNotNone(se)


if __name__ == "__main__":
    unittest.main()
