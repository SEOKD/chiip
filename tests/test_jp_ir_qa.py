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
