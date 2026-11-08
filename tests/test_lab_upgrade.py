"""Model Lab 고도화 — 그림자 판정·제안 보드·민감도 경로 (2026-11-08)"""
import csv
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lab"))
import pipeline as PL  # noqa: E402
import sensitivity as S  # noqa: E402
import shadow as SH  # noqa: E402


class TestShadowScore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self._s = (SH.LEDGER, SH.SCORE, SH.BASE, SH.prices)
        SH.LEDGER, SH.SCORE, SH.BASE = self.tmp / "ledger.csv", self.tmp / "score.csv", self.tmp

    def tearDown(self):
        SH.LEDGER, SH.SCORE, SH.BASE, SH.prices = self._s

    def test_challenger_with_better_ic_becomes_candidate(self):
        d0 = date(2026, 1, 1)
        days = [(d0 + timedelta(days=i)).isoformat() for i in range(40)]
        ents = [f"e{i}" for i in range(5)]
        growth = {f"e{i}": 1 + 0.01 * i for i in range(5)}   # e4가 가장 많이 오른다
        SH.prices = lambda: {e: [(d, 100 * growth[e] ** k) for k, d in enumerate(days)] for e in ents}
        with SH.LEDGER.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, SH.FIELDS)
            w.writeheader()
            for d in days[:10]:
                for i, e in enumerate(ents):
                    w.writerow({"date": d, "entity": e, "model": "baseline", "v0": 1, "exp_return": (-1) ** i * 0.01, "signal": "약함"})
                    w.writerow({"date": d, "entity": e, "model": "chal", "v0": 1, "exp_return": 0.01 * i, "signal": "강함" if i == 4 else "약함"})
        res = {r["model"]: r for r in SH.score((20,))}
        self.assertGreater(res["chal"]["ic"], res["baseline"]["ic"])
        self.assertTrue(res["chal"]["candidate"])
        self.assertGreater(res["chal"]["strong_excess"], 0)

    def test_spearman(self):
        self.assertAlmostEqual(SH.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)


class TestBoard(unittest.TestCase):
    def test_blocker_kinds(self):
        reg = {"prm-a": {"binding": None}, "prm-b": {"binding": "config/valuation_v2.yaml#x.y"}, "prm-c": {"binding": "config/alpha.yaml#z"}}
        mk = lambda params, status="proposed": {"id": "MLP-1", "status": status, "params": params, "judge": None, "approval": False}
        self.assertTrue(PL.blockers(mk(["prm-a"]), reg, [], {})[0].startswith("코드 연결 없음"))
        self.assertTrue(PL.blockers(mk(["prm-c"]), reg, [], {})[0].startswith("평가기 없음"))
        self.assertEqual(PL.blockers(mk(["prm-b"]), reg, [], {})[0], "그림자 미등록")
        self.assertEqual(PL.blockers(mk(["prm-b"]), reg, [{"param": "prm-b"}], {})[0], "관측 부족")


class TestSensitivityPaths(unittest.TestCase):
    def test_set_get(self):
        d = {"a": {"b": 1.0}}
        S.set_path(d, ["a", "b"], 2.0)
        self.assertEqual(S.get_path(d, ["a", "b"]), 2.0)

    def test_targets_are_v2_numeric(self):
        tg, _ = S.targets()
        self.assertTrue(tg)
        self.assertTrue(all(isinstance(t["value"], (int, float)) for t in tg))


if __name__ == "__main__":
    unittest.main()
