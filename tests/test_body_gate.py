"""본문 확인 관문 — 구글 뉴스 중계 주소·봇 차단·보류·Pulse 피드 read (마스터 지시 2026-11-14 "본문을 반드시 확인하는 구조")"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import fulltext as F  # noqa: E402
import pulse_feed  # noqa: E402
from pollers import common  # noqa: E402

KST = timezone(timedelta(hours=9))
GN = {"item_id": "src-defense-newsroom-gn:3212", "source_id": "src-defense-newsroom-gn", "doc_type": "보도자료",
      "url": "https://news.google.com/rss/articles/CBMiXYZ?oc=5", "publisher": "BAE Systems", "publisher_url": "https://www.example-defense.com",
      "title": "BAE Systems selected as a mission-enabling space technologies partner for NASA PRIMA astrophysics program - BAE Systems",
      "entities_matched": ["gb-bae"]}
BODY = "<p>" + ("BAE Systems will provide the cryogenic instrument assembly under a $40 million contract. " * 12) + "</p>"
WALL = '<html><head><META NAME="ROBOTS" CONTENT="NOINDEX"><script src="/_Incapsula_Resource?x=1"></script></head></html>'
ROBOTS = "User-agent: *\nAllow: /\nSitemap: https://www.example-defense.com/sitemap.xml\n"
SITEMAP = ("<urlset><url><loc>https://www.example-defense.com/en/article/unrelated-news</loc></url>"
           "<url><loc>https://www.example-defense.com/en/article/bae-systems-selected-as-a-mission-enabling-space-technologies-partner-for-nasa-prima-astrophysics-program</loc></url></urlset>")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "inbox").mkdir()
        (root / "state").mkdir()
        self.p = [mock.patch.object(common, "INBOX", root / "inbox"), mock.patch.object(common, "STATE", root / "state")]
        for x in self.p:
            x.start()
        self.root = root
        self.now = datetime(2026, 11, 14, 1, tzinfo=KST)

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()


class TestRoutes(Base):
    def test_relay_never_fetched_directly(self):
        calls = []
        with mock.patch.object(F, "_get", lambda url, ua=None, timeout=20: calls.append(url) or WALL):
            ft = F.fetch(dict(GN, publisher_url=""), self.now)
        self.assertEqual(ft["status"], "fail")
        self.assertFalse(any("news.google.com" in u for u in calls))   # robots.txt가 막은 중계 주소는 열지 않는다
        self.assertIn("query", ft["search"])
        self.assertNotIn(" - BAE Systems", ft["search"]["query"])

    def test_bot_wall_not_bypassed(self):
        with mock.patch.object(F, "_get", lambda url, ua=None, timeout=20: WALL):
            ft = F.fetch(dict(GN), self.now)
        self.assertEqual(ft["status"], "fail")
        self.assertIn("우회하지 않음", ft["why"])

    def test_publisher_sitemap_route(self):
        pages = {"https://www.example-defense.com/robots.txt": ROBOTS, "https://www.example-defense.com/sitemap.xml": SITEMAP}
        with mock.patch.object(F, "_get", lambda url, ua=None, timeout=20: pages.get(url, BODY)):
            ft = F.fetch(dict(GN), self.now)
        self.assertEqual(ft["status"], "ok")
        self.assertEqual(ft["route"], "발행사 사이트맵")
        self.assertIn("prima-astrophysics", ft["url"])
        self.assertTrue(any("$40 million" in k for k in ft["kpi"]))

    def test_robots_disallow_blocks_article(self):
        pages = {"https://www.example-defense.com/robots.txt": ROBOTS.replace("Allow: /", "Disallow: /en/article/"),
                 "https://www.example-defense.com/sitemap.xml": SITEMAP}
        with mock.patch.object(F, "_get", lambda url, ua=None, timeout=20: pages.get(url, BODY)):
            ft = F.fetch(dict(GN), self.now)
        self.assertEqual(ft["status"], "fail")
        self.assertIn("robots.txt가 기사 주소를 막음", ft["why"])

    def test_same_title_copy_in_inbox(self):
        day = common.INBOX / "20261114"
        day.mkdir()
        (day / "src-prn_x.json").write_text(json.dumps({"item_id": "src-prn:x", "source_id": "src-prn", "url": "https://www.prnewswire.com/bae-prima.html",
                                                       "title": "BAE Systems selected as a mission-enabling space technologies partner for NASA PRIMA astrophysics program"}), encoding="utf-8")
        with mock.patch.object(F, "_get", lambda url, ua=None, timeout=20: BODY if "prnewswire" in url else WALL):
            ft = F.fetch(dict(GN), self.now)
        self.assertEqual(ft["status"], "ok")
        self.assertTrue(ft["route"].startswith("같은 제목 다른 원천"))

    def test_all_types_opens_news(self):
        it = dict(GN, doc_type="기사", fulltext=None)
        F.enrich([it], self.now, fetcher=lambda i, n: {"status": "ok", "kpi": []})
        self.assertIsNone(it["fulltext"])   # 기본은 기사 유형을 열지 않는다
        F.enrich([it], self.now, fetcher=lambda i, n: {"status": "ok", "kpi": []}, all_types=True)
        self.assertEqual(it["fulltext"]["status"], "ok")


class TestHold(Base):
    def test_gate_holds_then_sends_when_read(self):
        import run_poll
        it = dict(GN)
        fail = lambda i, n: {"status": "fail", "why": "봇 차단 화면 — 우회하지 않음", "search": F.search_query(i)}
        out = run_poll.body_gate([(it, "P1", "방위 수주")], fetch=fail)
        self.assertEqual(out, [])   # 못 읽으면 보내지 않는다
        self.assertEqual(F.held()[0]["tries"], 1)
        out = run_poll.body_gate([], fetch=fail)
        self.assertEqual(F.held()[0]["tries"], 2)
        self.assertEqual(len(F.for_model(self.now)), 1)   # 두 번 실패하면 Pulse 모델 회차로
        F.offered([GN["item_id"]], self.now)
        self.assertEqual(F.for_model(self.now + timedelta(minutes=10)), [])   # 한 시간에 한 번만
        ok = lambda i, n: {"status": "ok", "kpi": ["$40 million contract"], "url": "https://x", "excerpt": BODY}
        out = run_poll.body_gate([], fetch=ok)
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0][0]["_held"])
        F.release(GN["item_id"], "sent")
        self.assertEqual(F.held(), [])

    def test_gives_up_without_sending(self):
        import run_poll
        fail = lambda i, n: {"status": "fail", "why": "x"}
        run_poll.body_gate([(dict(GN), "P1", "r")], fetch=fail)
        for _ in range(F.HOLD_TRIES * 2):
            self.assertEqual(run_poll.body_gate([], fetch=fail), [])
        self.assertEqual(F.held(), [])
        self.assertIn("given_up", (common.STATE / "fulltext_hold.log").read_text(encoding="utf-8"))


class TestFeedGate(unittest.TestCase):
    def test_feed_requires_read_url(self):
        d = {"time": "09:00", "items": [{"name": "BAE Systems", "code": "BA", "read": "https://news.google.com/rss/articles/x"}],
             "brief": [{"name": "Lockheed", "line": "x"}]}
        self.assertEqual(pulse_feed.unread(d), ["BAE Systems BA", "Lockheed"])
        d["items"][0]["read"] = "https://www.prnewswire.com/bae.html"
        d["brief"][0]["read"] = "https://www.sec.gov/Archives/x.htm"
        self.assertEqual(pulse_feed.unread(d), [])


if __name__ == "__main__":
    unittest.main()


class TestHeadlineAlpha(Base):
    def test_headline_moving_alpha_is_shared(self):
        import run_poll
        it = dict(GN, entities_matched=["co-bae"])
        fail = lambda i, n: {"status": "fail", "why": "봇 차단 화면 — 우회하지 않음"}
        judge = lambda batch: [{"item_id": b["item_id"], "moves": True, "component": "upside", "move": 1.0, "reason": "NASA 우주 임무 신규 수주"} for b in batch]
        with mock.patch.object(run_poll, "_alpha_rows", lambda: {"co-bae": {"name": "BAE Systems", "total": 3.3, "components": {"upside": 4.0}}}):
            out = run_poll.body_gate([(it, "P1", "방위 수주")], fetch=fail, judge=judge)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0]["_headline"]["component"], "upside")
        self.assertEqual(F.held(), [])   # 보류하지 않는다
        lines = run_poll.headline_lines(out[0][0]["_headline"], "봇 차단 화면 — 우회하지 않음")
        self.assertTrue(lines[0].startswith("본문 미확인 · 헤드라인 기준"))
        self.assertIn("상방 +1.0", lines[1])

    def test_small_or_no_move_is_held(self):
        import run_poll
        it = dict(GN, entities_matched=["co-bae"])
        fail = lambda i, n: {"status": "fail", "why": "x"}
        judge = lambda batch: [{"item_id": b["item_id"], "moves": True, "component": "gap", "move": 0.2, "reason": "작다"} for b in batch]
        with mock.patch.object(run_poll, "_alpha_rows", lambda: {"co-bae": {"name": "BAE", "total": 3.3, "components": {}}}):
            self.assertEqual(run_poll.body_gate([(it, "P1", "r")], fetch=fail, judge=judge), [])
        self.assertEqual(len(F.held()), 1)
        self.assertEqual(run_poll.headline_alpha([dict(GN, entities_matched=["zz-none"])], judge, rows={}), {})   # 알파 점수 없는 회사는 판정하지 않는다

    def test_feed_headline_alpha_passes(self):
        d = {"items": [{"name": "BAE", "read": "", "headline_alpha": "상방 +1.0 — NASA 우주 임무 수주"}]}
        self.assertEqual(pulse_feed.unread(d), [])


class TestFeedTidy(unittest.TestCase):
    def test_footer_lines_removed_content_kept(self):
        import notify
        t = "제목\n\n\n본문 · 근거\n\n1차 판정·미검증 · 공개 자료 기반 분석이며 투자 권유가 아님\n**구매 등급·목표주가 모두 규칙이 계산한 모델 값 · 투자 권유 아님 · 1차 판정, 미검증**\n"
        out = notify.feed_tidy(t)
        self.assertEqual(out, "제목\n\n본문 · 근거")
        self.assertIn("투자 권유 아님 — 다른 말", notify.feed_tidy("투자 권유 아님 — 다른 말"))
