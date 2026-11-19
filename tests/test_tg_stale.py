"""텔레그램 채널 무소식·이전 감지(2026-11-19 aethersemiresearch → aethersemiconductor 이전을 13일 놓친 뒤)"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import tg_channels as T  # noqa: E402
from pollers import common  # noqa: E402


class Stale(unittest.TestCase):
    def test_moved_and_disabled(self):
        now = common.now_kst()
        old = (now - timedelta(days=9)).isoformat()
        posts = {"a": {1: {"at": old, "text": "새로운 채널인 https://t.me/newchan 로 옮겼습니다"}},
                 "b": {1: {"at": now.isoformat(), "text": "x"}},
                 "c": {1: {"at": old, "text": "y"}}}
        cfg = {"channels": [{"handle": "a"}, {"handle": "b"}, {"handle": "c", "disabled": True}]}
        with mock.patch.object(T, "config", return_value=cfg), mock.patch.object(T, "load", side_effect=lambda h: posts[h]):
            self.assertEqual(T.stale_channels(now), [{"handle": "a", "days": 9, "moved_to": "newchan"}])


if __name__ == "__main__":
    unittest.main()
