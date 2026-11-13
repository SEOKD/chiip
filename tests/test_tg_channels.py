"""공개 텔레그램 채널 수집 (마스터 지시 2026-11-01)"""
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import tg_channels as tg  # noqa: E402

PAGE = '''<div class="tgme_widget_message_wrap js-widget_message_wrap"><div class="tgme_widget_message" data-post="merITz_tech/19281">
<a class="tgme_widget_message_forwarded_from_name" href="x"><span>원채널</span></a>
<div class="tgme_widget_message_text js-message_text" dir="auto">GE Vernova 수주&amp;증가<br/>둘째 줄 <a href="https://www.sec.gov/a">링크</a></div>
<time datetime="2026-11-01T09:00:00+00:00" class="time">09:00</time></div></div>
<div class="tgme_widget_message_wrap js-widget_message_wrap"><div class="tgme_widget_message" data-post="merITz_tech/19282"><div class="tgme_widget_message_photo_wrap"></div>
<time datetime="2026-11-01T09:05:00+00:00" class="time">09:05</time></div></div>'''
CFG = {"min_chars": 20, "keywords": ["반도체"], "channels": [{"handle": "merITz_tech", "always": True}, {"handle": "marketfeed"}]}
TECH = re.compile("HBM")


class TestChannels(unittest.TestCase):
    def test_parse_keeps_text_link_and_forward(self):
        rows = tg.parse(PAGE, "S")
        self.assertEqual(rows[0]["channel"], "merITz_tech")
        self.assertIn("수주&증가\n둘째 줄", rows[0]["text"])
        self.assertEqual(rows[0]["forwarded_from"], "원채널")
        self.assertEqual(rows[0]["link"], "https://www.sec.gov/a")
        self.assertTrue(rows[0]["at"].startswith("2026-11-01T18:00"))   # 한국 시각으로 저장한다
        self.assertEqual(rows[1]["text"], "")
        self.assertTrue(rows[1]["media"])

    def test_closed_preview_returns_none(self):
        self.assertIsNone(tg.collect("x", get=lambda u: "<html>no posts</html>", pause=0))

    def test_collect_keeps_first_seen(self):
        store = {}
        with mock.patch.object(tg, "load", lambda h: dict(store)), mock.patch.object(tg, "save", lambda h, p: store.update(p)):
            self.assertEqual(tg.collect("merITz_tech", get=lambda u: PAGE, pause=0), 2)
            self.assertEqual(store[19281]["seen"], tg.BASELINE)   # 처음 읽은 채널의 지난 글은 Pulse에 새 글로 가지 않는다
            self.assertEqual(tg.collect("merITz_tech", get=lambda u: PAGE, pause=0), 0)
            self.assertEqual(store[19281]["seen"], tg.BASELINE)

    def test_relevance(self):
        base = {"channel": "marketfeed"}
        with mock.patch.object(tg.common, "match_entities", lambda t: []):
            self.assertTrue(tg.relevant({**base, "text": "HBM 공급 늘어난다는 소식이 나왔습니다 오늘"}, CFG, TECH))
            self.assertTrue(tg.relevant({**base, "text": "반도체 업황이 바뀌고 있다는 시장의 이야기입니다"}, CFG, TECH))
            self.assertFalse(tg.relevant({**base, "text": "오늘 환율과 금리가 움직인 이야기를 적어 둡니다"}, CFG, TECH))
            self.assertFalse(tg.relevant({**base, "text": "HBM"}, CFG, TECH))
            self.assertTrue(tg.relevant({"channel": "meritz_tech", "text": "오늘 환율과 금리가 움직인 이야기를 적어 둡니다"}, CFG, TECH))

    def test_reposts_collapse_to_first_channel(self):
        t = "삼성전자가 새로운 공급 계약을 맺었다는 소식이 전해졌다 시장 반응 주목"
        rows = tg.dedupe([{"channel": "a", "text": t}, {"channel": "b", "text": t + "!!"}, {"channel": "c", "text": "다른 글"}])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["also"], ["b"])

    def test_recent_poll_is_not_repeated(self):
        now = tg.common.now_kst()
        with mock.patch.object(tg, "poll") as p, mock.patch.object(tg.common, "load_state", lambda n, d=None: {"at": tg.common.iso(now)}):
            self.assertFalse(tg.poll_if_stale(now))
            p.assert_not_called()

    def test_stale_collection_reads_again(self):
        now = tg.common.now_kst()
        old = tg.common.iso(now - tg.timedelta(minutes=30))
        with mock.patch.object(tg, "poll") as p, mock.patch.object(tg.common, "load_state", lambda n, d=None: {"at": old}):
            self.assertTrue(tg.poll_if_stale(now))
            p.assert_called_once()

    def test_unsupported_post_is_filled_from_its_page(self):
        posts = {1: {"id": 1, "text": "", "unsupported": True, "url": "u"}}
        tg.fill_unsupported("c", posts, lambda u: '<meta property="og:description" content="본문 &amp; 줄">', pause=0)
        self.assertEqual(posts[1]["text"], "본문 & 줄")

    def test_link_only_post_uses_preview_title(self):
        page = '''<div class="tgme_widget_message_wrap"><div data-post="c/5"><div class="link_preview_title" dir="auto">제목입니다</div><time datetime="2026-11-01T09:00:00+00:00"></time></div></div>'''
        self.assertEqual(tg.parse(page)[0]["text"], "제목입니다")

    def test_missing_post_returns_none(self):
        self.assertIsNone(tg.read_post("c", 9, "소개", lambda u: '<meta property="og:description" content="소개">', "S"))

    def test_by_id_reads_new_posts_only(self):
        store = {7: {"id": 7, "text": "옛 글"}}
        page = lambda u: '<meta property="og:description" content="%s">' % ("소개" if not u.endswith(("/8", "/9")) else "새 글")
        with mock.patch.object(tg, "load", lambda h: dict(store)), mock.patch.object(tg, "save", lambda h, p: store.update(p)):
            self.assertEqual(tg.collect_by_id("c", get=page, pause=0, misses=3), 2)
        self.assertEqual(sorted(store), [7, 8, 9])

    def test_feed_paragraphs(self):
        import notify
        long = " ".join(["첫 문장은 충분히 길게 씁니다 매출이 늘었고 이익도 늘었습니다."] * 6)
        self.assertGreater(notify.readable(long).count("\n\n"), 1)
        self.assertEqual(notify.readable("요약 문장\n· 하나\n· 둘"), "요약 문장\n\n· 하나\n· 둘")
        self.assertEqual(notify.readable("**■ 결론**\n- 하나\n- 둘"), "**■ 결론**\n- 하나\n- 둘")

    def test_config_has_all_channels(self):
        self.assertEqual(len(tg.config()["channels"]), 17)   # 2026-11-10 js_Enews 추가(마스터 지시)


if __name__ == "__main__":
    unittest.main()
