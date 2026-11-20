"""전력 입법·규제 추적 — 단계 낱말 판정·앞선 단계만 후보·장부는 1차 출처 URL로만(마스터 지시 2026-11-20)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import power_policy as P  # noqa: E402


class Policy(unittest.TestCase):
    def setUp(self):
        self.c = P.cfg()

    def test_stage_words(self):
        self.assertEqual(P.stage_of("Senate passes bipartisan permitting reform bill", "bill", self.c), "상원 통과")
        self.assertEqual(P.stage_of("Senate adopts substitute amendment 69-27", "bill", self.c), "상원 토론 종결")
        self.assertEqual(P.stage_of("FERC issues final rule on large load interconnection", "rule", self.c), "최종 규칙")

    def test_only_ahead_is_jump(self):
        self.assertTrue(P.ahead("상원 통과", "상원 토론 종결", "bill", self.c))
        self.assertFalse(P.ahead("위원회 통과", "상원 토론 종결", "bill", self.c))

    def test_classify(self):
        item = {"id": "x", "kind": "bill", "match": "permitting"}
        es = [{"link": "a", "title": "Senate passes permitting reform", "desc": ""}, {"link": "b", "title": "Unrelated chip news", "desc": ""}]
        r = P.classify(item, es, {"x": {"stage": "상원 토론 종결"}}, self.c, set())
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0]["jump"])


class Congress(unittest.TestCase):
    def test_action_stage(self):   # Congress.gov 행동 문구(2026-11-20 키 연결)
        self.assertEqual(P.action_stage("Cloture on the measure invoked in Senate by Yea-Nay Vote. 65 - 31."), "상원 토론 종결")
        self.assertEqual(P.action_stage("Passed Senate with an amendment by Yea-Nay Vote. 68 - 30."), "상원 통과")
        self.assertEqual(P.action_stage("Became Public Law No: 119-60."), "대통령 서명")
        self.assertIsNone(P.action_stage("Considered by Senate."))


if __name__ == "__main__":
    unittest.main()
