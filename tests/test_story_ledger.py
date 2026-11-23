"""보낸 사건 장부 — 실시간 알림·Pulse 중복 관문(마스터 지시 2026-11-22 "Pulse가 중복된 정보를 여러 번 텔레그램 피드로 보내는 것 같다")"""
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import common  # noqa: E402
import pulse_feed as F  # noqa: E402
import story_ledger as L  # noqa: E402

NOW = common.now_kst().replace(hour=12, minute=0, second=0, microsecond=0)


def at(minutes_ago):
    return common.iso(NOW - timedelta(minutes=minutes_ago))


class Ledger(unittest.TestCase):
    def setUp(self):
        self.mem = {"story_ledger": {"rows": []}, "alerts": {}}
        self.p1 = mock.patch.object(common, "load_state", side_effect=lambda n, d=None: self.mem.get(n, d))
        self.p2 = mock.patch.object(common, "save_state", side_effect=lambda n, v: self.mem.__setitem__(n, v))
        self.p3 = mock.patch.object(L, "codes_of", side_effect=lambda ents: {"INTC"} if "co-intel" in (ents or []) else set())
        for p in (self.p1, self.p2, self.p3):
            p.start()

    def tearDown(self):
        mock.patch.stopall()

    def alert(self, mins, title, url, ents=("co-intel",)):
        self.mem["alerts"][title[:8]] = {"level": "P1", "sent_at": at(mins), "title": title, "url": url, "entities": list(ents)}

    def feed(self, items=(), brief=()):
        return {"time": "12:00", "items": list(items), "brief": list(brief)}

    def item(self, **kw):
        x = {"name": "인텔", "code": "INTC", "event": "마이크로소프트, 자체 Azure 칩에 EMIB 패키징 채택 발표", "insight": 5,
             "links": [["인텔 발표", "https://www.intel.com/newsroom/emib"]], "read": "https://www.intel.com/newsroom/emib"}
        x.update(kw)
        return x

    def test_same_ticker_minutes_after_alert_dropped(self):
        self.alert(9, "Intel landing Microsoft for EMIB is a 'positive' - Reuters", "https://news.google.com/rss/articles/abc?oc=5")
        d, drop, rows = F.dedupe(self.feed([self.item()]), Path("x/20261121_1200_feed.json"), NOW)
        self.assertEqual(d["items"], [])
        self.assertIn("20분 안", drop[0][1])

    def test_deep_judgment_of_alert_dropped(self):   # 2026-11-24 마스터 지시 "Pulse로 중복된 소식을 전달하지 마라"
        self.alert(9, "Intel landing Microsoft for EMIB", "https://news.google.com/rss/articles/abc")
        d, drop, _ = F.dedupe(self.feed([self.item(insight=8)]), Path("x/20261121_1200_feed.json"), NOW)
        self.assertEqual(d["items"], [])

    def test_update_also_dropped(self):
        L.record([{"codes": ["INTC"], "text": "마이크로소프트, 자체 Azure 칩에 EMIB 패키징 채택 발표", "urls": [L.norm_url("https://www.intel.com/newsroom/emib")], "feed": "20261121_0110"}],
                 NOW - timedelta(hours=2))
        d, drop, _ = F.dedupe(self.feed([self.item(update="구글도 EMIB 채택 확인")]), Path("x/20261121_1200_feed.json"), NOW)
        self.assertEqual(d["items"], [])
        self.assertEqual(drop[0][1].split(" — ")[0], "같은 원문")

    def test_relay_links_cut_and_relay_only_dropped(self):   # 오리지널 소스만
        x = self.item(links=[["보도자료(Business Wire)", "https://www.businesswire.com/news/home/1/en/"], ["보도자료 사본", "https://www.stocktitan.net/news/BWXT/x.html"]])
        d, drop, _ = F.dedupe(self.feed([x]), Path("x/20261121_1200_feed.json"), NOW)
        self.assertEqual([l[1] for l in d["items"][0]["links"]], ["https://www.businesswire.com/news/home/1/en/"])
        y = self.item(links=[["요약", "https://seekingalpha.com/news/1"]], read="https://seekingalpha.com/news/1")
        d, drop, _ = F.dedupe(self.feed([y]), Path("x/20261121_1200_feed.json"), NOW)
        self.assertEqual(d["items"], [])
        self.assertIn("오리지널 소스 없음", drop[0][1])

    def test_similar_korean_head_same_ticker_dropped_hours_later(self):
        L.record([{"codes": ["000660"], "text": "키옥시아 CB 주식 전환 결정 — 간접 지분 14.1%", "urls": [], "feed": "20261120_1614"}], NOW - timedelta(minutes=98))
        b = {"name": "SK하이닉스", "code": "000660", "line": "키옥시아 CB 보통주 전환 결정 — 간접 지분 14.1% 직접 보유로", "link": ["보도", "https://example.com/b"], "read": "https://example.com/b"}
        d, drop, _ = F.dedupe(self.feed(brief=[b]), Path("x/20261120_1756_feed.json"), NOW)
        self.assertEqual(d["brief"], [])

    def test_different_story_same_ticker_later_kept(self):
        L.record([{"codes": ["INTC"], "text": "18A 첫 외부 고객 계약 — 고객명 비공개", "urls": [], "feed": "20261121_0800"}], NOW - timedelta(hours=3))
        d, drop, _ = F.dedupe(self.feed([self.item()]), Path("x/20261121_1200_feed.json"), NOW)
        self.assertEqual(drop, [])

    def test_rerun_same_feed_not_self_duplicate(self):
        src = Path("x/20261121_1200_feed.json")
        _, _, rows = F.dedupe(self.feed([self.item()]), src, NOW)
        L.record(rows, NOW)
        d, drop, _ = F.dedupe(self.feed([self.item()]), src, NOW)
        self.assertEqual(drop, [])

    def test_realtime_alert_blocked_after_pulse(self):
        import promote
        L.record([{"codes": ["INTC"], "text": "마이크로소프트 EMIB 채택", "urls": [L.norm_url("https://www.intel.com/newsroom/emib")], "feed": "f"}], NOW - timedelta(minutes=3))
        it = {"item_id": "x1", "title": "Intel and Microsoft expand partnership on EMIB packaging - Intel", "url": "https://www.intel.com/newsroom/emib?utm_source=x",
              "entities_matched": ["co-intel"]}
        self.assertTrue(str(promote.duplicate_of(it, now=NOW)).startswith("Pulse"))


if __name__ == "__main__":
    unittest.main()
