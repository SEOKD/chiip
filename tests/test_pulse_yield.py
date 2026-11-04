"""펄스 문턱 양보 — 앱 예약 회차가 잠금을 쥐면 실패로 세지 않는다(2026-11-05 오경보)"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import pulse_trigger  # noqa: E402


class TestYield(unittest.TestCase):
    def lock(self, minutes_ago):
        now = pulse_trigger.common.now_kst()
        return {"lock": pulse_trigger.common.iso(now - timedelta(minutes=minutes_ago))}

    def test_fresh_lock_is_busy(self):
        with mock.patch.object(pulse_trigger.common, "load_state", return_value=self.lock(1)):
            self.assertTrue(pulse_trigger.busy())

    def test_stale_or_no_lock_is_free(self):
        with mock.patch.object(pulse_trigger.common, "load_state", return_value=self.lock(pulse_trigger.pulse.LOCK_MIN + 1)):
            self.assertFalse(pulse_trigger.busy())
        with mock.patch.object(pulse_trigger.common, "load_state", return_value={}):
            self.assertFalse(pulse_trigger.busy())


if __name__ == "__main__":
    unittest.main()
