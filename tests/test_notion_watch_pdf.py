"""노션 감시기 PDF 본문 읽기(2026-11-20 마스터 지시 "Notion의 Telegram Feed 페이지에 올라오는 pdf도 읽도록 하라")"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import notion_watch as W  # noqa: E402
import notion_library as NL  # noqa: E402


class TestPdfBody(unittest.TestCase):
    def setUp(self):
        self.orig = NL.CACHE
        NL.CACHE = Path(tempfile.mkdtemp())

    def tearDown(self):
        NL.CACHE = self.orig

    def test_cached_text_used(self):
        (NL.CACHE / "b1.txt").write_text("사이버보안 투자 아이디어 " * 30, encoding="utf-8")
        out = W.pdf_body("b1", None)
        self.assertTrue(out.startswith("[PDF 본문]"))
        self.assertIn("사이버보안", out)

    def test_image_pdf_flagged(self):
        (NL.CACHE / "b2.txt").write_text("짧음", encoding="utf-8")
        self.assertIn("그림 위주", W.pdf_body("b2", None))

    def test_page_text_reads_pdf_block(self):
        blocks = [{"id": "b3", "type": "pdf", "pdf": {"name": "x.pdf", "file": {"url": "u"}}, "has_children": False}]
        with mock.patch.object(W, "children", return_value=blocks), mock.patch.object(W, "pdf_body", return_value="[PDF 본문]\n내용") as pb:
            text = W.page_text("p")
        pb.assert_called_once_with("b3", "u")
        self.assertIn("[첨부 x.pdf]", text)
        self.assertIn("내용", text)


if __name__ == "__main__":
    unittest.main()
