"""일본 IR 질의응답 수집기 시험 (마스터 지시 2026-10-29 — easyconomics에 일본 어닝콜이 없어 일본어 IR 페이지의 Q&A 전문을 가져온다)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))

from pollers import jp_ir_qa  # noqa: E402
import pulse  # noqa: E402


class TestQaLinks(unittest.TestCase):
    PAGE = """<h1>IR資料室 決算説明会</h1>
    <a href="/ir/library/pdf/2026q2_presentation.pdf">2026年3月期 第2四半期 決算説明会資料</a>
    <a href="/ir/library/pdf/2026q2_qa.pdf">第2四半期 決算説明会 質疑応答（要旨）</a>
    <a href="/ir/faq/">よくあるご質問</a>
    <a href="/en/ir/library/pdf/2026q2_qa_e.pdf">Q&amp;A (English)</a>
    <a href="https://other.example.com/qa.pdf">他社 質疑応答</a>
    <a href="/ir/stock/qa.html">株式に関するQ&amp;A</a>"""

    def test_finds_japanese_qa_only(self):
        found = jp_ir_qa.qa_links(self.PAGE, "https://www.example.co.jp/ir/library/")
        self.assertEqual(list(found), ["https://www.example.co.jp/ir/library/pdf/2026q2_qa.pdf"])   # FAQ·영문판·타사·주식 Q&A 제외

    def test_pulse_accepts_japanese_qa(self):
        self.assertEqual(pulse.class_of("src-jp-ir-qa"), "IR 질의응답")
        self.assertTrue(pulse.relevant({"title": "東京エレクトロン IR 質疑応答", "language": "ja"}, "IR 질의응답"))

    def test_html_to_text(self):
        t = jp_ir_qa.to_text("https://x.co.jp/qa.html", "<html><nav>メニュー</nav><p>Q. 受注の見通しは？</p><p>A. 堅調です。</p></html>".encode("utf-8"))
        self.assertIn("受注の見通し", t)
        self.assertNotIn("メニュー", t)


if __name__ == "__main__":
    unittest.main()


class TestProcedureA(unittest.TestCase):
    """지시문 A(2026-10-30) — 우선순위·출처 등급·외부 전사·게재 시차"""
    HTML = ('<a href="/ir/qa_2q.pdf">決算説明会 主な質疑応答</a><a href="/ir/script.pdf">決算説明会 スクリプト付き資料</a>'
            '<a href="/ir/slides.pdf">決算説明会資料</a><a href="https://finance.logmi.jp/articles/1">ログミーFinance</a>'
            '<a href="https://www.youtube.com/watch?v=x">決算説明会 動画</a><a href="/en/ir/qa_e.pdf">Q&A summary earnings briefing</a>'
            '<a href="/faq/">よくあるご質問</a>')

    def test_scan_tiers_and_grades(self):
        from pollers import jp_ir_qa as j
        s = j.scan_page(self.HTML, "https://www.example.co.jp/ir/library/")
        d = s["docs"]
        self.assertEqual(d["https://www.example.co.jp/ir/qa_2q.pdf"][:3], (1, "Q&A", "B"))       # 主な質疑応答 = 회사 편집 요지
        self.assertEqual(d["https://www.example.co.jp/ir/script.pdf"][2], "A")                   # 스크립트 = 회사 원문(발표부)
        self.assertEqual(d["https://www.example.co.jp/en/ir/qa_e.pdf"][4], "en")                 # 영문판도 본다
        self.assertIn("https://www.example.co.jp/ir/slides.pdf", s["materials"])
        self.assertIn("https://finance.logmi.jp/articles/1", s["external"])
        self.assertFalse(any("faq" in u for u in d))                                              # 일반 FAQ 제외
        p = j.profile_of("x", s)
        self.assertEqual(p["qa_format"], "요지")
        self.assertIn("로그미", p["external"])

    def test_business_days_skip_tse_holidays(self):
        from datetime import date
        from pollers import jp_ir_qa as j
        self.assertEqual(j.add_bdays(date(2026, 10, 30), 3, ["2026-11-03"]), date(2026, 11, 5))   # 금 → 월·수·목(11/3 휴장)
