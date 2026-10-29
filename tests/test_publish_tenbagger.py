"""텐배거 리포트 발행 묶음 — GitHub 보기 마크다운·차트 SVG, 노션·텔레그램 순서 관문(마스터 지시 2026-10-30)"""
import json
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
sys.path.insert(0, str(ROOT / "scripts"))

import publish_tenbagger as pt  # noqa: E402
import report_md  # noqa: E402

DOC = {"title": "테스트 리포트", "date": "2026-10-30", "ticker": "TST", "company": "Test Co", "biz": "테스트 사업",
       "verdict": {"view": "판단", "confidence": "중", "alpha": 6.0},
       "sections": [{"h2": "주가", "blocks": [
           {"type": "p", "text": "매출 $1.2B"},
           {"type": "chart", "chart": {"kind": "line", "title": "종가", "series": [{"name": "종가", "color": "c", "points": [["2026-09", 10], ["2026-10", 12]]}]}},
           {"type": "chart", "chart": {"kind": "bars", "title": "매출", "categories": ["1Q", "2Q"], "series": [{"name": "매출", "color": "a", "values": [1, 2]}]}}]}],
       "sources": ["출처"]}


class TestReportMd(unittest.TestCase):
    def test_standalone_svg_has_no_css_vars_and_parses(self):
        svg = report_md.standalone(DOC["sections"][0]["blocks"][1]["chart"])
        self.assertNotIn("var(--", svg)
        self.assertIn('xmlns="http://www.w3.org/2000/svg"', svg)
        self.assertIn("종가", svg)   # 범례가 그림 안에
        ET.fromstring(svg)

    def test_markdown_places_images_and_escapes_dollar(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "20261030_TST.json"
            src.write_text(json.dumps(DOC, ensure_ascii=False), encoding="utf-8")
            r = report_md.build(src)
            md = Path(r["md"]).read_text(encoding="utf-8")
            self.assertEqual(len(r["charts"]), 2)
            self.assertIn("![그림 1](charts/20261030_TST_1.svg)", md)
            self.assertIn("![그림 2](charts/20261030_TST_2.svg)", md)
            self.assertIn("\\$1.2B", md)   # GitHub 수식으로 읽히지 않게
            self.assertTrue(md.startswith("# 텐배거 리포트 2026-10-30"))


class TestDeliveryGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        rep = Path(self.tmp.name)
        self.src = rep / "20261030_TST.json"
        self.src.write_text(json.dumps(DOC, ensure_ascii=False), encoding="utf-8")
        self.src.with_suffix(".html").write_text("<html></html>", encoding="utf-8")
        self.p = [patch.object(pt, "REP", rep), patch.object(pt, "STATE", rep / "delivery"), patch.object(pt, "LEDGER", rep / "delivery.csv"),
                  patch.object(pt, "NOTION_LOG", rep / "notion_log.csv"), patch.object(pt, "ROOT", rep)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def test_send_refused_before_github(self):
        with self.assertRaises(SystemExit):
            pt.send(self.src, dry=True)

    def test_notion_fail_then_followup(self):
        r = pt.prepare(self.src, dry=True)
        self.assertTrue(r["github_md"].endswith("20261030_TST.md"))
        self.assertTrue(Path(self.tmp.name, r["notion_body"]).exists())
        pt.notion(self.src, fail="커넥터 오류")
        s1 = pt.send(self.src, "캡션", dry=True)
        self.assertTrue(s1["sent"])
        self.assertFalse(s1["notion_ok"])
        self.assertIn("노션 게시 실패", s1["text"])
        self.assertIn("HTML 보기 링크 게시 실패", s1["text"])   # Artifact가 없으면 GitHub 마크다운으로 대신
        self.assertEqual(len(pt.pending()), 1)
        pt.notion(self.src, page="https://app.notion.com/p/abc")
        pt.artifact(self.src, url="https://claude.ai/code/artifact/q")
        s2 = pt.send(self.src, dry=True)
        self.assertIn("노션 게시 완료", s2["text"])
        self.assertEqual(pt.pending(), [])
        self.assertIn("skipped", pt.send(self.src, dry=True))   # 같은 리포트를 두 번 보내지 않는다

    def test_full_success_message_has_both_links(self):
        r = pt.prepare(self.src, dry=True)
        art = Path(self.tmp.name, r["artifact_page"]).read_text(encoding="utf-8")
        self.assertTrue(art.startswith("<title>TST 텐배거 리포트 10·30</title>"))   # 게시 뼈대가 씌워지므로 doctype·body 없음
        self.assertNotIn("<body>", art)
        pt.artifact(self.src, url="https://claude.ai/code/artifact/abc")
        pt.notion(self.src, page="https://app.notion.com/p/xyz")
        s = pt.send(self.src, "요약", dry=True)
        self.assertIn("📄 리포트 보기: https://claude.ai/code/artifact/abc", s["text"])
        self.assertIn("skipped", pt.send(self.src, dry=True))
        self.assertTrue(pt.send(self.src, "요약", dry=True, resend=True)["sent"])   # 경로가 바뀐 리포트는 다시 보낼 수 있다
        self.assertIn("https://app.notion.com/p/xyz", s["text"])
        self.assertEqual(pt.existing_notion("2026-10-30", "TST")[0], "https://app.notion.com/p/xyz")


if __name__ == "__main__":
    unittest.main()
