"""모델 사용 한도 관리(2026-11-24 점검 D1, radar/model_budget.py) — 한도 동안 헤드리스 회차를 띄우지 않고, 작업을 버리지 않는다"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import model_budget as MB  # noqa: E402
import pulse_trigger  # noqa: E402
import run_triage  # noqa: E402

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 24, 7, 54, tzinfo=KST)
FABLE = "You've hit your Fable limit · resets 4pm (Asia/Seoul). Switch to another model, or manage usage credits at https://claude.ai/settings/usage to continue."
WEEKLY = "claude 실패(1): You've hit your weekly limit · resets Nov 24, 4pm (Asia/Seoul)"


class TestParse(unittest.TestCase):
    def test_same_day_reset(self):
        self.assertEqual(MB.parse(FABLE, NOW), ("Fable", datetime(2026, 11, 24, 16, 0, tzinfo=KST)))

    def test_dated_reset_and_past_time_rolls_over(self):
        self.assertEqual(MB.parse(WEEKLY, datetime(2026, 11, 23, 7, 0, tzinfo=KST))[1], datetime(2026, 11, 24, 16, 0, tzinfo=KST))
        self.assertEqual(MB.parse("You've hit your weekly limit · resets 4pm (Asia/Seoul)", datetime(2026, 11, 24, 17, 0, tzinfo=KST))[1],
                         datetime(2026, 11, 25, 16, 0, tzinfo=KST))

    def test_utc_and_unreadable(self):
        self.assertEqual(MB.parse("You've hit your session limit · resets 7:30am (UTC)", NOW)[1], datetime(2026, 11, 24, 16, 30, tzinfo=KST))
        kind, until = MB.parse("You've hit your usage limit.", NOW)
        self.assertEqual(until, NOW + timedelta(minutes=MB.DEFAULT_HOLD_MIN))

    def test_headless_phrase_without_reset_holds_an_hour(self):   # claude -p 실제 문구(11/24 08:57 실행 장부)
        got = MB.parse("You've reached your Fable limit. Switch to another model, or manage usage credits at https://claude.ai/settings/usage", NOW)
        self.assertEqual(got, ("Fable", NOW + timedelta(minutes=MB.DEFAULT_HOLD_MIN)))

    def test_old_epoch_phrase(self):
        ts = int(datetime(2026, 11, 24, 16, 0, tzinfo=KST).timestamp())
        self.assertEqual(MB.parse(f"Claude AI usage limit reached|{ts}", NOW)[1], datetime(2026, 11, 24, 16, 0, tzinfo=KST))

    def test_not_a_limit(self):
        self.assertIsNone(MB.parse("종료 코드 1 · 관문 미실행", NOW))
        self.assertIsNone(MB.parse("HTTP Error 429: Too Many Requests", NOW))


class StateCase(unittest.TestCase):
    def setUp(self):
        self.st = {}
        for p in (mock.patch.object(MB.common, "load_state", side_effect=lambda name, d=None: dict(self.st.get(name, d if d is not None else {}))),
                  mock.patch.object(MB.common, "save_state", side_effect=lambda name, data: self.st.__setitem__(name, dict(data))),
                  mock.patch.object(MB.common, "record_health")):
            p.start()
            self.addCleanup(p.stop)


class TestHold(StateCase):
    def test_note_blocks_until_reset_then_clears(self):
        self.assertIsNone(MB.note("다른 오류", "t", NOW))
        st = MB.note(FABLE, "t", NOW)
        self.assertEqual(st["kind"], "Fable")
        self.assertTrue(MB.blocked(NOW + timedelta(hours=8)))
        self.assertIsNone(MB.blocked(datetime(2026, 11, 24, 16, MB.GRACE_MIN + 1, tzinfo=KST)))
        with self.assertRaises(MB.Hold):
            MB.guard(NOW + timedelta(minutes=5))

    def test_check_failure_raises_hold_only_for_limit(self):
        MB.check_failure("Permission denied", "t", NOW)   # 한도가 아니면 조용히 넘긴다
        with self.assertRaises(MB.Hold):
            MB.check_failure(WEEKLY, "t", NOW)

    def test_alert_once_per_hold(self):
        MB.note(FABLE, "t", NOW)
        with mock.patch("notify.send") as send:
            self.assertTrue(MB.alert_once(NOW + timedelta(minutes=1)))
            self.assertFalse(MB.alert_once(NOW + timedelta(minutes=6)))
        self.assertEqual(send.call_count, 1)
        self.assertIn("16:03", send.call_args.args[0])

    def test_hourly_reprobe_is_one_episode(self):   # 재개 시각 없는 문구 — 1시간 대기가 이어져도 알림은 한 번
        text = "You've reached your Fable limit. Switch to another model"
        MB.note(text, "t", NOW)
        with mock.patch("notify.send") as send:
            MB.alert_once(NOW + timedelta(minutes=1))
            later = NOW + timedelta(minutes=MB.DEFAULT_HOLD_MIN + MB.GRACE_MIN + 1)
            self.assertIsNone(MB.blocked(later))
            MB.note(text, "t", later)   # 한 시간 뒤 다시 걸림
            self.assertTrue(MB.blocked(later + timedelta(minutes=1)))
            self.assertFalse(MB.alert_once(later + timedelta(minutes=1)))
        self.assertEqual(send.call_count, 1)
        self.assertIn("다시 확인", send.call_args.args[0])


class TestTrigger(StateCase):
    def setUp(self):
        super().setUp()
        on = {**pulse_trigger.cfg(), "enabled": True, "urgent": {"enabled": False}}
        for p in (mock.patch.object(pulse_trigger, "cfg", return_value=on), mock.patch.object(pulse_trigger.common, "stay_awake"),
                  mock.patch.object(pulse_trigger.run_ledger, "record"), mock.patch.object(pulse_trigger, "app_stalled", return_value=None),
                  mock.patch.object(pulse_trigger.pulse, "run", return_value=(True, "모델 회차"))):
            p.start()
            self.addCleanup(p.stop)

    def test_blocked_never_launches_or_counts(self):
        MB.note(FABLE, "t", MB.common.now_kst())
        with mock.patch.object(pulse_trigger, "launch") as launch, mock.patch("notify.send") as send:
            pulse_trigger.main([])
            pulse_trigger.main([])
        launch.assert_not_called()
        self.assertEqual(send.call_count, 1)   # 한도 알림 한 번
        self.assertFalse((self.st.get("pulse_trigger") or {}).get("count"))

    def test_limit_failure_refunds_cap_and_holds(self):
        fields = {"error": "사용 한도(Fable)", "budget_hold": True}
        def fail(_):
            MB.note(FABLE, "pulse_trigger", MB.common.now_kst())
            return False, fields
        with mock.patch.object(pulse_trigger, "launch", side_effect=fail) as launch, mock.patch("notify.send"), mock.patch.object(pulse_trigger, "alert") as alert:
            pulse_trigger.main([])
            pulse_trigger.main([])
        self.assertEqual(launch.call_count, 1)
        alert.assert_not_called()   # '연속 실패'·'상한' 알림 대신 한도 알림
        day = MB.common.now_kst().strftime("%Y%m%d")
        self.assertEqual(self.st["pulse_trigger"]["count"][day], 0)


class TestRunClaude(StateCase):
    def test_guard_before_launch(self):
        MB.note(FABLE, "t", MB.common.now_kst())
        with mock.patch.object(run_triage.subprocess, "run") as run:
            with self.assertRaises(MB.Hold):
                run_triage.run_claude("p", "haiku")
        run.assert_not_called()

    def test_limit_text_in_failure_becomes_hold(self):
        proc = mock.Mock(returncode=1, stdout='{"is_error": true, "result": "%s"}' % FABLE.replace('"', ""), stderr="")
        with mock.patch.object(run_triage.subprocess, "run", return_value=proc), mock.patch.object(run_triage, "calls_today"), \
                mock.patch.object(run_triage, "claude_exe", return_value="claude"):
            with self.assertRaises(MB.Hold):
                run_triage.run_claude("p", "haiku")
        self.assertTrue(MB.blocked())


if __name__ == "__main__":
    unittest.main()
