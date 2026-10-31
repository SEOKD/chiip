"""딘스티커 읽기 전용 수집과 채널 발송 차단 (마스터 지시 2026-10-31)"""
import re
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import dticker  # noqa: E402
import notify  # noqa: E402


def post(pid, text, when="2026-10-31T00:54:24+00:00", extra=""):
    return (f'<div class="tgme_widget_message_wrap js-widget_message_wrap"><div class="tgme_widget_message" data-post="d_ticker/{pid}">{extra}'
            f'<div class="tgme_widget_message_text js-message_text" dir="auto">{text}</div>'
            f'<time datetime="{when}" class="time">09:54</time></div></div>')


NOW = datetime(2026, 10, 31, 15, tzinfo=dticker.common.KST)


class TestParse(unittest.TestCase):
    def test_keeps_lines_links_and_kst_time(self):
        p = dticker.parse(post(4040, '구글 &amp; 국방부<br/><br/>- <a href="x">협의</a> 중'))[0]
        self.assertEqual((p["id"], p["text"], p["url"]), (4040, "구글 & 국방부\n\n- 협의 중", "https://t.me/d_ticker/4040"))
        self.assertTrue(p["at"].startswith("2026-10-31T09:54"))

    def test_forward_and_photo_flags(self):
        p = dticker.parse(post(1, "글", extra='<div class="tgme_widget_message_forwarded_from"></div><a class="tgme_widget_message_photo_wrap"></a>'))[0]
        self.assertTrue(p["forwarded"] and p["photo"])


class TestCollect(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.path = Path(self.d.name) / "posts.jsonl"

    def test_walks_back_then_stops_at_known_and_updates_edits(self):
        pages = {dticker.PAGE: post(11, "새 글") + post(12, "둘째"), f"{dticker.PAGE}?before=11": post(9, "옛 글")}
        calls = []
        get = lambda u: calls.append(u) or pages.get(u, "")
        self.assertEqual(dticker.collect(get, self.path, 0, NOW), 3)
        calls.clear()
        pages[dticker.PAGE] = post(12, "고친 둘째") + post(13, "셋째")
        self.assertEqual(dticker.collect(get, self.path, 0, NOW), 1)
        self.assertEqual(calls, [dticker.PAGE])
        self.assertEqual(dticker.load(self.path)[12]["text"], "고친 둘째")

    def test_about_matches_ticker_as_word(self):
        dticker.collect(lambda u: post(1, "INTC 기판 부족") + post(2, "MINTCO 소식") + post(3, "인텔 실적") if u == dticker.PAGE else "", self.path, 0, NOW)
        self.assertCountEqual([p["id"] for p in dticker.about(["INTC", "인텔"], path=self.path, now=NOW)], [1, 3])

    def test_agent_posts_are_not_master_opinion(self):
        dticker.collect(lambda u: post(1, "인텔 분석\n\n※ 에이전트 결과물입니다") + post(2, "인텔 의견") if u == dticker.PAGE else "", self.path, 0, NOW)
        self.assertEqual([p["id"] for p in dticker.about(["인텔"], path=self.path, now=NOW)], [2])

    def test_columns_filter(self):
        dticker.collect(lambda u: post(1, "가" * dticker.COLUMN_CHARS) + post(2, "짧은 글") if u == dticker.PAGE else "", self.path, 0, NOW)
        self.assertEqual([p["id"] for p in dticker.recent(14, True, self.path, NOW)], [1])


class TestReadOnly(unittest.TestCase):
    def test_collector_has_no_write_path(self):
        src = (ROOT / "radar" / "dticker.py").read_text(encoding="utf-8")
        code = re.sub(r'""".*?"""', "", src, flags=re.S)
        for word in ("api.telegram.org", "sendMessage", "notify", "http_post", "urlopen", "TELEGRAM_BOT_TOKEN"):
            self.assertNotIn(word, code)

    def test_only_personal_chat_is_allowed(self):
        self.assertTrue(notify.private_chat("123456"))
        for chat in ("-1001234567890", "@d_ticker", "d_ticker", "-100", ""):
            self.assertFalse(notify.private_chat(chat))

    def test_send_refuses_channel_before_network(self):
        for chat in ("-1001234567890", "@d_ticker"):
            with mock.patch.object(notify.common, "load_env", return_value={"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": chat}), mock.patch.object(notify.urllib.request, "urlopen") as net, mock.patch.object(notify, "_log") as log:
                self.assertFalse(notify.send("글", "P1"))
            net.assert_not_called()
            self.assertIn("개인 대화방 아님", log.call_args[0][0])

    def test_send_document_refuses_channel(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.txt"
            f.write_text("글", encoding="utf-8")
            with mock.patch.object(notify.common, "load_env", return_value={"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "@d_ticker"}), mock.patch.object(notify.urllib.request, "urlopen") as net, mock.patch.object(notify, "_log"):
                self.assertFalse(notify.send_document(f, "캡션"))
            net.assert_not_called()


if __name__ == "__main__":
    unittest.main()
