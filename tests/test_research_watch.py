"""리서치·투자자 감시(research_watch) 오프라인 테스트 — HTTP는 가짜 응답으로 대체

실행: py -m unittest discover -s tests -v
"""
import json
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))

from pollers import common, research_watch as rw  # noqa: E402

CFG = {
    "x_api": {"key_env": "X_BEARER_TOKEN", "base": "https://api.x.com/2", "monthly_post_cap": 3,
              "exclude": ["replies", "retweets"], "max_results": 20},
    "accounts": [
        {"id": "rw-a", "name": "A Research", "kind": "리서치기관", "feed": "https://a.example/feed", "x_handle": "a_res"},
        {"id": "rw-b", "name": "B Fund", "kind": "투자자", "x_handle": "bfund"},
        {"id": "rw-c", "name": "C Ghost", "kind": "투자자", "x_handle": "ghost"},
    ],
}


def rss_feed(dates):
    items = "".join(f"<item><title>Post {i} on SK hynix HBM4</title><link>https://a.example/p{i}</link>"
                    f"<pubDate>{d}</pubDate><description>body {i}</description></item>" for i, d in enumerate(dates))
    return f"<rss><channel>{items}</channel></rss>".encode()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p_state = mock.patch.object(common, "STATE", Path(self.tmp.name) / "state")
        self.p_inbox = mock.patch.object(common, "INBOX", Path(self.tmp.name) / "inbox")
        self.p_cfg = mock.patch.object(rw, "load_cfg", return_value=CFG)
        for p in (self.p_state, self.p_inbox, self.p_cfg):
            p.start()

    def tearDown(self):
        for p in (self.p_state, self.p_inbox, self.p_cfg):
            p.stop()
        self.tmp.cleanup()


class TestFeeds(Base):
    def test_only_recent_posts(self):
        fmt = "%a, %d %b %Y %H:%M:%S +0900"
        now = common.now_kst()
        raw = rss_feed([now.strftime(fmt), (now - timedelta(days=10)).strftime(fmt)])
        with mock.patch.object(common, "http_get", return_value=raw):
            items = rw.poll_feeds()
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual((it["source_id"], it["doc_type"], it["publisher"], it["research_id"]),
                         ("src-research-feeds", "리서치", "A Research", "rw-a"))
        self.assertIn("co-skhynix", it["entities_matched"])

    def test_all_feeds_fail_raises(self):
        with mock.patch.object(common, "http_get", side_effect=OSError("down")):
            with self.assertRaises(RuntimeError):
                rw.poll_feeds()


class TestX(Base):
    def fake_http(self, calls):
        def _get(url, params=None, headers=None, timeout=20):
            calls.append(url)
            assert headers["Authorization"] == "Bearer T"
            if "/users/by" in url:
                return json.dumps({"data": [{"id": "1", "username": "a_res"}, {"id": "2", "username": "BFund"}]}).encode()
            uid = url.split("/users/")[1].split("/")[0]
            posts = [{"id": f"{uid}0{i}", "text": f"short {i}", "created_at": "2026-10-28T01:00:00.000Z",
                      "note_post": {"text": f"long note {i} about Micron HBM"} if i == 0 else None,
                      "public_metrics": {"like_count": 5}} for i in range(2)]
            return json.dumps({"data": posts, "meta": {"newest_id": f"{uid}01", "result_count": 2}}).encode()
        return _get

    def test_timeline_ids_since_and_cap(self):
        calls = []
        with mock.patch.object(common, "http_get", side_effect=self.fake_http(calls)):
            items = rw.poll_x({"X_BEARER_TOKEN": "T"})
        # 사용자 조회 1회 + a_res 타임라인(2건) + bfund 타임라인(2건, 상한 3 → 그 뒤 중단). ghost는 조회 실패로 건너뜀
        self.assertEqual(len(items), 4)
        self.assertTrue(items[0]["title"].startswith("@a_res: long note 0"))
        self.assertEqual(items[0]["url"], "https://x.com/a_res/status/100")
        self.assertEqual(items[0]["doc_type"], "SNS")
        self.assertIn("start_time=", calls[1])
        st = common.load_state("research_x")
        self.assertEqual(st["since"], {"a_res": "101", "bfund": "201"})
        self.assertEqual(st["missing"], ["ghost"])
        self.assertEqual(st["posts"], 4)
        # 다음 실행: 이미 상한(3) 초과 → 타임라인 호출 없음, 사용자 재조회 없음
        calls.clear()
        with mock.patch.object(common, "http_get", side_effect=self.fake_http(calls)):
            self.assertEqual(rw.poll_x({"X_BEARER_TOKEN": "T"}), [])
        self.assertEqual(calls, [])

    def test_since_id_used(self):
        common.save_state("research_x", {"month": common.now_kst().strftime("%Y-%m"), "posts": 0,
                                         "ids": {"a_res": "1"}, "missing": ["bfund", "ghost"], "since": {"a_res": "99"}})
        calls = []
        with mock.patch.object(common, "http_get", side_effect=self.fake_http(calls)):
            rw.poll_x({"X_BEARER_TOKEN": "T"})
        self.assertEqual(len(calls), 1)
        self.assertIn("since_id=99", calls[0])

    def test_no_key(self):
        with self.assertRaises(RuntimeError):
            rw.poll_x({})


class TestDigestAndTelegram(Base):
    def test_digest_groups_by_account(self):
        it = common.make_item("src-research-feeds", "u1", "https://a.example/p", "HBM4 note", common.iso(common.now_kst()),
                              "리서치", "en", extra=rw._extra(CFG["accounts"][0]))
        common.save_new_items([it])
        out = rw.digest(16)
        self.assertIn("A Research", out)
        self.assertIn("HBM4 note", out)

    def test_telegram_routing(self):
        import notify
        # X 글은 텔레그램 허용(§21.12), 뉴스레터 RSS는 브리프 전용
        self.assertTrue(notify.telegram_allowed({"source_id": "src-research-x", "doc_type": "SNS", "title": "a"})[0])
        self.assertFalse(notify.telegram_allowed({"source_id": "src-research-feeds", "doc_type": "리서치", "title": "a"})[0])
        for src, dt in (("src-policy-cn", "규제·정책"), ("src-legistar", "규제·정책"), ("src-assoc-gn", "학회·협회")):
            self.assertTrue(notify.telegram_allowed({"source_id": src, "doc_type": dt, "title": "x - 中华人民共和国商务部"})[0])


if __name__ == "__main__":
    unittest.main()
