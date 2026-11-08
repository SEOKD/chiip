"""Industry Report '사건 때 심층' 논리 틀 (마스터 지시 2026-11-08)"""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "industry"))
import event_frame as ef  # noqa: E402

CFG = ef.config()
SRC = {"source": "s", "url": "u"}
DP = {
    "id": "t", "date": "2026-11-08", "title": "제목", "industry": "산업", "event": {"name": "사건"},
    "groups": [{"id": "G1", "name": "설비"}, {"id": "G2", "name": "발전"}],
    "reaction": {"window": "1주", "benchmark": "SPY", "items": [{"group": "G1", "name": "a", "ret": -12, "rel": -10}, {"group": "G2", "name": "b", "ret": -2, "rel": 0}]},
    "money": [{"kind": "PAC 기부", "who": "x", "amount": 1, "party": "민주", **SRC}, {"kind": "PAC 기부", "who": "y", "amount": 1, "party": "공화", **SRC},
              {"kind": "로비(LD)", "who": "z", "amount": 1e6, "party": "정당 구분 없음", **SRC}],
    "incentives": {"delay": [{"text": "지연", **SRC}], "act": [{"text": "실행", **SRC}]},
    "channels": [{"id": "C1", "name": "중단", "level": "주", "stage": "공약", "window": "2027", "p": 0.5, "source": "a", "impact": {"G1": -4, "G2": -2}},
                 {"id": "C2", "name": "허가", "level": "연방 의회", "stage": "발의", "window": "2026-12", "p": 0.2, "source": "b", "impact": {"G1": 3}},
                 {"id": "C3", "name": "비용", "level": "주", "stage": "규제기관 명령", "window": "2027", "p": 0.8, "source": "c", "impact": {"G1": -1}}],
    "counter": [{"text": "반론", **SRC}] * 3,
    "checkpoints": [{"date": "2027-04-30", "what": "w", "p": 0.7}] * 3,
}


class TestGate(unittest.TestCase):
    def test_passes(self):
        self.assertEqual(ef.gate(DP, CFG), [])

    def test_one_party_money_is_rejected(self):   # 한쪽 돈만 보면 가설을 확인만 하게 된다
        d = copy.deepcopy(DP)
        d["money"] = [m for m in d["money"] if m["party"] != "공화"]
        self.assertTrue(any("양당" in x for x in ef.gate(d, CFG)))

    def test_bad_stage_and_missing_counter(self):
        d = copy.deepcopy(DP)
        d["channels"][0]["stage"] = "확정"   # 금지표 — 단계 이름은 정해진 것만
        d["counter"] = d["counter"][:1]
        bad = " ".join(ef.gate(d, CFG))
        self.assertIn("단계", bad)
        self.assertIn("반대", bad)


class TestCompute(unittest.TestCase):
    def test_gap_rating_and_extremes(self):
        rows = {r["id"]: r for r in ef.compute(DP, CFG)}
        g1 = rows["G1"]
        self.assertAlmostEqual(g1["expected"], 0.5 * -4 + 0.2 * 3 + 0.8 * -1)
        self.assertAlmostEqual(g1["gap"], g1["expected"] - (-10))
        self.assertEqual(g1["rule"], "Attractive")
        self.assertEqual(g1["worst"], -5.0)   # 불리한 경로만 전부
        self.assertEqual(g1["best"], 3.0)
        self.assertEqual(rows["G2"]["rule"], "In-Line")

    def test_confound_lowers_confidence_and_debate_one_step(self):
        d = copy.deepcopy(DP)
        d["reaction"]["confound"] = "AI 디레버리징"
        d["debate"] = {"G1": {"adjust": -3, "reason": "교란"}}   # 세 단계를 요구해도 한 단계만
        g1 = {r["id"]: r for r in ef.compute(d, CFG)}["G1"]
        self.assertAlmostEqual(g1["conf"], 0.75 - CFG["rating"]["confound_penalty"])
        self.assertEqual((g1["rule"], g1["rating"]), ("Attractive", "In-Line"))

    def test_build_has_eight_steps(self):
        d = ef.build(copy.deepcopy(DP), CFG)
        self.assertEqual([s["h2"] for s in d["sections"]][:8], ef.STEPS)


class TestPredictions(unittest.TestCase):
    def test_register_once(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "predictions.csv"
            p.write_text("pred_id,made_on,thesis_id,statement,metric,target,deadline,probability,basis,resolved_on,outcome,notes,owner,origin\n", encoding="utf-8")
            with mock.patch.object(ef, "PRED", p):
                self.assertEqual(ef.register(DP, "2026-11-08"), 3)
                self.assertEqual(ef.register(DP, "2026-11-08"), 0)   # 사후 수정·중복 없이
            self.assertEqual(len(p.read_text(encoding="utf-8").strip().splitlines()), 4)


if __name__ == "__main__":
    unittest.main()
