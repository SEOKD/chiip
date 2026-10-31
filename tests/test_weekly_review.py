import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "weekly"))
sys.path.insert(0, str(ROOT / "radar"))
import publish_weekly  # noqa: E402
import render  # noqa: E402


def doc():
    return json.loads((ROOT / "outputs" / "brief" / "2026-W44_weekly.json").read_text(encoding="utf-8"))


class TestPublish(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        (self.d / "2026-W44_weekly.json").write_text(json.dumps({"week": "2026-W44", "week_no": 44, "period": "10/26~10/30", "headline": "제목", "bullets": ["결론"]}, ensure_ascii=False), encoding="utf-8")
        (self.d / "2026-W44_weekly.md").write_text("# 제목줄\n\n본문\n", encoding="utf-8")
        (self.d / "artifact_links.md").write_text("", encoding="utf-8")
        self.p = [mock.patch.object(publish_weekly, "BRIEF", self.d), mock.patch.object(publish_weekly, "STATE", self.d / "delivery"), mock.patch.object(publish_weekly, "LEDGER", self.d / "delivery.csv"),
                  mock.patch.object(publish_weekly, "ROOT", self.d.parent)]
        for x in self.p:
            x.start()
            self.addCleanup(x.stop)
        self.sent = []
        fake = mock.Mock(send=lambda text, level, md=False: self.sent.append(text) or True, run_ledger=mock.Mock())
        n = mock.patch.dict(sys.modules, {"notify": fake})
        n.start()
        self.addCleanup(n.stop)

    def rewrite(self):
        (self.d / "2026-W44_weekly.md").write_text("# 제목줄\n\n고친 본문\n", encoding="utf-8")

    def test_send_needs_artifact_of_this_version(self):
        with self.assertRaises(SystemExit):
            publish_weekly.send("2026-W44")
        publish_weekly.artifact("2026-W44", "https://claude.ai/artifact/x")
        self.rewrite()
        with self.assertRaises(SystemExit):
            publish_weekly.send("2026-W44")

    def test_same_version_once_and_rewrite_goes_as_revision(self):
        publish_weekly.artifact("2026-W44", "https://claude.ai/artifact/x")
        publish_weekly.notion("2026-W44", "https://notion/p")
        publish_weekly.send("2026-W44")
        self.assertIn("skipped", publish_weekly.send("2026-W44"))
        self.assertEqual(len(self.sent), 1)
        self.assertIn("[노션](https://notion/p)", self.sent[0])
        self.assertNotIn("수정판", self.sent[0])
        self.rewrite()
        self.assertEqual(publish_weekly.pending(), [{"week": "2026-W44", "left": ["artifact", "notion", "telegram"]}])
        publish_weekly.artifact("2026-W44", "https://claude.ai/artifact/x")
        publish_weekly.send("2026-W44")
        self.assertIn("수정판", self.sent[1])
        self.assertIn("노션 게시 실패", self.sent[1])   # 노션이 이번 판이 아니면 옛 페이지를 최신처럼 알리지 않는다

    def test_notion_body_keeps_page_link_for_rewrite(self):
        publish_weekly.artifact("2026-W44", "https://claude.ai/artifact/x")
        publish_weekly.notion("2026-W44", "https://notion/p")
        with mock.patch.object(publish_weekly, "ROOT", self.d):
            res = publish_weekly.notion_body("2026-W44")
        self.assertEqual(res["existing_page"], "https://notion/p")
        text = (self.d / "2026-W44_notion.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("[차트와 표 전체 보기](https://claude.ai/artifact/x)"))
        self.assertNotIn("제목줄", text)


class TestWeeklyReview(unittest.TestCase):
    def setUp(self):
        self.c = render.cfg()

    def test_gate_passes_good_report(self):
        render.check(doc(), self.c)
        movers = render.load_movers("2026-W44", self.c)
        render.lint(render.to_md(doc(), movers), self.c)
        self.assertEqual([r["title"] for r in movers][-2:], ["Taiwan", "Hong Kong"])
        self.assertIn("+33%｜글라우코스｜녹내장 스텐트", render.ticker_block(doc(), movers))
        self.assertEqual(render.themes(movers)[1], 80)

    def test_gate_rejects(self):
        d = doc()
        d["changes"] = d["changes"][:1]
        with self.assertRaises(ValueError):
            render.check(d, self.c)
        d = doc()
        d["headline"] = "가" * 80
        with self.assertRaises(ValueError):
            render.check(d, self.c)
        for bad in ("매출은 미확인이다", "원천 보류로 비었다", "台光電 매출", "knowledge/x.csv 없음", "D-20261030-01"):
            with self.assertRaises(ValueError):
                render.lint(bad, self.c)

    def test_tw_hk_names(self):
        import notify
        self.assertEqual(notify.tw_hk_names("台光電·廣達"), "엘리트머티리얼즈·콴타")


class TestFeedCodes(unittest.TestCase):
    def test_code_gloss(self):
        import notify
        t = notify.brand("사유: T2 실적이면 P1이나 2차 재인용. T2 다시")
        self.assertIn("T2(글로벌 밸류체인 기업)", t)
        self.assertIn("P1(즉시 알림 등급)이나", t)
        self.assertEqual(t.count("T2("), 1)
        self.assertEqual(notify.code_gloss("S-1 T2(이미)"), "S-1 T2(이미)")

    def test_line_chart_keeps_time_order(self):
        sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
        import report_html
        c = {"kind": "line", "title": "t", "unit": "$", "series": [{"name": "a", "color": "a", "points": [["9/4", 1], ["10/2", 2], ["10/30", 3]]}]}
        svg = report_html.chart_line(c)
        self.assertLess(svg.index("9/4"), svg.index("10/30"))


if __name__ == "__main__":
    unittest.main()
