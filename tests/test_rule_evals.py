"""규칙 준수 측정기·펄스 건별 점검·발송 관문·에이전트 수집 트랙"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "lab"))
import literature  # noqa: E402
import notify  # noqa: E402
import pulse_check  # noqa: E402
import rule_evals  # noqa: E402

GOOD = "⚡ ① 넷앱(NTAP)｜실적\n\n스토리지 회사\n\n**판단**\n\n· 3Q 매출 $3B\n\n[8-K](https://sec.gov/a)\n\n─────\n\n간단히\n· 링크 없는 한 줄"


class TestRules(unittest.TestCase):
    def test_every_rule_has_working_examples(self):
        self.assertEqual(rule_evals.self_test(rule_evals.load_rules()), [])

    def test_rule_applies_only_from_its_date(self):
        rule = {"id": "x", "rule": "x", "scope": ["*.txt"], "since": "2026-10-30", "forbid": "금칙"}
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "20261029_tg.txt").write_text("금칙", encoding="utf-8")
            (Path(d) / "20261030_tg.txt").write_text("금칙", encoding="utf-8")
            row = rule_evals.score([rule], root=Path(d))[0]
        self.assertEqual((row["checked"], row["failed"]), (1, 1))

    def test_gate_fails_on_either_split(self):
        row = {"id": "x", "in": [10, 1], "out": [10, 3]}
        self.assertEqual(rule_evals.gate([row], {"x": {"in": [10, 1], "out": [10, 1]}})[0][:2], ("x", "out"))
        self.assertEqual(rule_evals.gate([row], {"x": {"in": [10, 2], "out": [10, 3]}}), [])
        self.assertEqual(rule_evals.gate([{"id": "x", "in": [0, 0], "out": [0, 0]}], {"x": {"in": [9, 0], "out": [9, 0]}}), [])


class TestPulseCheck(unittest.TestCase):
    def test_clean_block_and_brief_lines(self):
        self.assertEqual(pulse_check.check(GOOD), [])

    def test_quarter_labels_are_not_numbers(self):
        self.assertEqual(len(pulse_check.NUM.findall("3Q FY26 10/29 매출 $3B +5%")), 2)

    def test_unlinked_block(self):
        text = GOOD.replace("[8-K](https://sec.gov/a)", "")
        self.assertEqual(len(pulse_check.unlinked(text)), 1)
        self.assertEqual(pulse_check.unlinked(text.replace("· 3Q", "출처 미확인\n· 3Q")), [])

    def test_send_refuses_unlinked_pulse_only(self):
        text = GOOD.replace("[8-K](https://sec.gov/a)", "")
        with mock.patch.object(notify, "_log") as log, mock.patch.object(notify.common, "load_env", return_value={}):
            self.assertFalse(notify.send(text, "PULSE", md=True))
            self.assertIn("출처 링크 없음", log.call_args[0][0])
            notify.send(text, "P1")
            self.assertNotIn("차단", log.call_args[0][0])


class TestAgentTrack(unittest.TestCase):
    def test_agent_keywords_score_separately(self):
        score, tags = literature.relevance("Instruction stacking collapse in agents", "", literature._AGENT_KW)
        self.assertGreaterEqual(score, literature.AGENT_MIN)
        self.assertIn("지시문·맥락", tags)
        self.assertLess(literature.relevance("Orbital games planning", "", literature._AGENT_KW)[0], literature.AGENT_MIN)


if __name__ == "__main__":
    unittest.main()
