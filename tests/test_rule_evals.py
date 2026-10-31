"""규칙 준수 측정기·펄스 건별 점검·발송 관문·에이전트 수집 트랙"""
import json
import re
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
import pulse_trigger  # noqa: E402
import run_ledger  # noqa: E402
import verifier_lock  # noqa: E402
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
        row = {"id": "x", "in": [20, 2], "out": [20, 10]}
        self.assertEqual(rule_evals.gate([row], {"x": {"in": [20, 2], "out": [20, 2]}})[0][:2], ("x", "out"))
        self.assertEqual(rule_evals.gate([row], {"x": {"in": [20, 2], "out": [20, 10]}}), [])

    def test_gate_ignores_noise_and_small_samples(self):
        row = {"id": "x", "in": [20, 3], "out": [5, 5]}
        self.assertEqual(rule_evals.gate([row], {"x": {"in": [20, 2], "out": [20, 0]}}), [])


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


class TestInstructionSize(unittest.TestCase):
    def test_claude_md_stays_common_only(self):
        text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertLess(text.count("\n"), 200)
        self.assertLess(len(text), 12000)

    def test_index_points_to_real_files(self):
        text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
        names = set(re.findall(r"docs/channels/(\w+)\.md", text))
        self.assertEqual(names, {p.stem for p in (ROOT / "docs" / "channels").glob("*.md")})


class TestLedger(unittest.TestCase):
    def repo(self, d):
        root = Path(d)
        (root / ".git").mkdir()
        (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (root / ".git" / "packed-refs").write_text("abcdef1234567 refs/heads/main\n", encoding="utf-8")
        (root / "CLAUDE.md").write_text("규칙", encoding="utf-8")
        return root

    def test_row_links_commit_instructions_and_no_body(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(run_ledger, "ENABLED", True):
            root = self.repo(d)
            run_ledger.record("send", "chiip-pulse", root=root, text_sha=run_ledger.text_sha("본문"), ok=True)
            row = run_ledger.rows(root=root)[0]
        self.assertEqual(row["commit"], "abcdef1234")
        self.assertTrue(row["instructions"])
        self.assertNotIn("본문", str(row))

    def test_report_links_files_and_counts_empty_gates(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(run_ledger, "ENABLED", True):
            root = self.repo(d)
            run_ledger.record("gate", "chiip-pulse", root=root, outcome="종료")
            run_ledger.record("gate", "chiip-pulse", root=root, outcome="진행")
            run_ledger.record("send", "chiip-pulse", root=root, text_sha=run_ledger.text_sha("보낸 글\n"))
            out = root / "outputs" / "article" / "sources"
            out.mkdir(parents=True)
            (out / "1_tg.txt").write_text("보낸 글", encoding="utf-8")
            (out / "2_tg.txt").write_text("안 보낸 글", encoding="utf-8")
            res = run_ledger.report(root=root)
        self.assertEqual((res["tg_files"], res["tg_linked"], res["empty_gate_rate"]), (2, 1, 0.5))

    def test_ledger_failure_does_not_break_send(self):
        with mock.patch.object(run_ledger, "ENABLED", True), mock.patch.object(run_ledger, "git_commit", side_effect=OSError):
            run_ledger.record("send", "x")

    def test_split_message_is_one_row(self):
        with mock.patch.object(run_ledger, "send_row") as row, mock.patch.object(notify.common, "load_env", return_value={}), mock.patch.object(notify, "_log"):
            notify.send("가" * 9000, "P1")
        self.assertEqual(row.call_count, 1)


class TestPulseTrigger(unittest.TestCase):
    def setUp(self):
        self.st = {}
        on = {**pulse_trigger.cfg(), "enabled": True}
        self.patches = [mock.patch.object(pulse_trigger, "cfg", return_value=on),
                        mock.patch.object(pulse_trigger.common, "load_state", side_effect=lambda *a: dict(self.st)),
                        mock.patch.object(pulse_trigger.common, "save_state", side_effect=lambda _, s: self.st.update(s)),
                        mock.patch.object(pulse_trigger.common, "stay_awake"),
                        mock.patch.object(pulse_trigger.run_ledger, "record")]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_no_material_never_starts_model(self):
        with mock.patch.object(pulse_trigger.pulse, "run", return_value=(None, "→ 종료")) as gate, mock.patch.object(pulse_trigger, "launch") as launch:
            self.assertEqual(pulse_trigger.main([]), 0)
        launch.assert_not_called()
        self.assertEqual(gate.call_args.kwargs, {"peek": True})
        self.assertIn("heartbeat", self.st)

    def test_disabled_never_starts_model_or_alerts(self):
        with mock.patch.object(pulse_trigger, "cfg", return_value={"enabled": False}), mock.patch.object(pulse_trigger.pulse, "run") as gate, mock.patch.object(pulse_trigger, "alert") as alert:
            self.assertEqual(pulse_trigger.main([]), 0)
            pulse_trigger.run()
        gate.assert_not_called()
        alert.assert_not_called()

    def test_runs_without_stdout_like_pyw(self):
        with mock.patch.object(pulse_trigger.sys, "stdout", None), mock.patch.object(pulse_trigger.pulse, "run", return_value=(None, "→ 종료")):
            self.assertEqual(pulse_trigger.main([]), 0)

    def test_never_ran_alerts_once(self):
        with mock.patch.object(pulse_trigger, "alert") as alert:
            pulse_trigger.run()
            pulse_trigger.run()
        self.assertEqual(alert.call_count, 1)

    def test_failures_alert_once_at_threshold(self):
        with mock.patch.object(pulse_trigger.pulse, "run", return_value=(True, "모델 회차")), mock.patch.object(pulse_trigger, "launch", return_value=(False, {"error": "x"})), mock.patch.object(pulse_trigger, "alert") as alert:
            for _ in range(3):
                pulse_trigger.main([])
        self.assertEqual(alert.call_count, 1)
        self.assertEqual(self.st["fails"], 3)

    def test_daily_cap_stops_model(self):
        day = pulse_trigger.common.now_kst().strftime("%Y%m%d")
        self.st["count"] = {day: pulse_trigger.cfg()["daily_model_cap"]}
        with mock.patch.object(pulse_trigger.pulse, "run", return_value=(True, "모델 회차")), mock.patch.object(pulse_trigger, "launch") as launch, mock.patch.object(pulse_trigger, "alert") as alert:
            pulse_trigger.main([])
            pulse_trigger.main([])
        launch.assert_not_called()
        self.assertEqual(alert.call_count, 1)

    def test_exit_zero_without_gate_is_failure(self):
        proc = mock.Mock(returncode=0, stdout=json.dumps({"permission_denials": [{"tool_name": "Bash", "tool_input": {"command": "cd x; py y"}}], "total_cost_usd": 0.6}))
        with mock.patch.object(pulse_trigger.subprocess, "run", return_value=proc), mock.patch.object(pulse_trigger.shutil, "which", return_value="claude"), mock.patch.object(pulse_trigger, "gate_mark", return_value="같음"):
            ok, fields = pulse_trigger.launch(pulse_trigger.cfg())
        self.assertFalse(ok)
        self.assertFalse(fields["ran"])
        self.assertEqual(fields["denied"], ["Bash: cd x; py y"])

    def test_gate_moved_is_success(self):
        proc = mock.Mock(returncode=0, stdout="{}")
        with mock.patch.object(pulse_trigger.subprocess, "run", return_value=proc), mock.patch.object(pulse_trigger.shutil, "which", return_value="claude"), mock.patch.object(pulse_trigger, "gate_mark", side_effect=["전", "후"]):
            self.assertTrue(pulse_trigger.launch(pulse_trigger.cfg())[0])

    def test_command_is_bounded_and_read_only_on_tradingview(self):
        c = pulse_trigger.cfg()
        cmd = pulse_trigger.command(c, "claude", "지시")
        self.assertIn("dontAsk", cmd)
        self.assertIn("--max-budget-usd", cmd)
        self.assertNotIn("alert", " ".join(c["allowed_tools"]))
        self.assertNotIn("mcp__claude_ai_TradingView__*", c["allowed_tools"])

    def test_stale_heartbeat_alerts_once(self):
        self.st["heartbeat"] = "2026-01-01T00:00:00+09:00"
        with mock.patch.object(pulse_trigger, "alert") as alert:
            pulse_trigger.run()
            pulse_trigger.run()
        self.assertEqual(alert.call_count, 1)


class TestPeek(unittest.TestCase):
    def test_peek_does_not_touch_state(self):
        with mock.patch.object(pulse_trigger.pulse, "inbox_items", return_value=[{"source_class": "x", "title": "t"}]), mock.patch.object(pulse_trigger.pulse, "score", return_value=1), \
                mock.patch.object(pulse_trigger.pulse, "fetch_alerts", return_value=[]), mock.patch.object(pulse_trigger.pulse, "alpha_queue", return_value=[]), \
                mock.patch.object(pulse_trigger.common, "load_state", return_value={}), mock.patch.object(pulse_trigger.common, "save_state") as save:
            for name in ("fetch_papers", "fetch_deals", "fetch_financing", "fetch_shorts", "fetch_new_listings", "fetch_consumer_spikes"):
                setattr(self, name, mock.patch.object(pulse_trigger.pulse, name, return_value=[]))
                getattr(self, name).start()
                self.addCleanup(getattr(self, name).stop)
            material, msg = pulse_trigger.pulse.run(peek=True)
        self.assertTrue(material)
        self.assertIn("모델 회차", msg)
        save.assert_not_called()


class TestVerifierLock(unittest.TestCase):
    def test_repository_matches_lock(self):
        self.assertEqual(verifier_lock.check(), [])

    def test_detects_change(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for f in verifier_lock.FILES:
                (root / f).parent.mkdir(parents=True, exist_ok=True)
                (root / f).write_bytes(b"a\r\n")
            (root / "evals" / "verifier.lock").write_text(json.dumps(verifier_lock.digest(root)), encoding="utf-8")
            self.assertEqual(verifier_lock.check(root), [])
            (root / "evals" / "rules.yaml").write_bytes(b"b\n")
            self.assertEqual(verifier_lock.check(root), ["evals/rules.yaml"])


class TestAgentTrack(unittest.TestCase):
    def test_agent_keywords_score_separately(self):
        score, tags = literature.relevance("Instruction stacking collapse in agents", "", literature._AGENT_KW)
        self.assertGreaterEqual(score, literature.AGENT_MIN)
        self.assertIn("지시문·맥락", tags)
        self.assertLess(literature.relevance("Orbital games planning", "", literature._AGENT_KW)[0], literature.AGENT_MIN)


if __name__ == "__main__":
    unittest.main()
