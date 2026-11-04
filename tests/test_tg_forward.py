"""텔레그램 전달 글 출처 (2026-11-04 채널 점검)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar" / "pollers"))
import tg_channels as t  # noqa: E402


class TestForward(unittest.TestCase):
    def test_names(self):
        named = '<div class="tgme_widget_message_forwarded_from">Forwarded from <a class="tgme_widget_message_forwarded_from_name" href="x"><span dir="auto">마켓피드</span></a></div>'
        hidden = '<div class="tgme_widget_message_forwarded_from accent_color">Forwarded from&nbsp;<span class="tgme_widget_message_forwarded_from_name"><span dir="auto"></span></span></div>'
        self.assertEqual(t.fwd_name(named), "마켓피드")
        self.assertEqual(t.fwd_name(hidden), "(이름 숨김)")
        self.assertEqual(t.fwd_name("<div>보통 글</div>"), "")


if __name__ == "__main__":
    unittest.main()
