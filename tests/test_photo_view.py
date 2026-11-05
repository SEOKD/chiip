"""제품·시설 실사 사진(마스터 지시 2026-11-05) — 자유 라이선스 판정과 블록·렌더"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import photo_view  # noqa: E402
import report_html  # noqa: E402


class TestPhoto(unittest.TestCase):
    def test_free_license(self):
        for ok in ("CC BY-SA 4.0", "CC BY 2.0", "CC0", "Public domain"):
            self.assertTrue(photo_view.FREE.match(ok))
        for bad in ("Fair use", "All rights reserved", ""):
            self.assertFalse(photo_view.FREE.match(bad))

    def test_block_skips_missing_and_renders(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(photo_view, "DIR", Path(d)):
            dp = {"photos": [{"for": "product", "name": "A", "file": "File:a.jpg", "caption": "c"}, {"for": "site", "name": "S", "file": "File:none.jpg"}]}
            f = photo_view.path_of("File:a.jpg")
            f.write_bytes(b"\xff\xd8x")
            f.with_suffix(".json").write_text('{"file":"File:a.jpg","license":"CC0","artist":"x","mime":"image/jpeg"}', encoding="utf-8")
            b = photo_view.block(dp, "product")
            self.assertEqual(b["items"][0]["jpg"], f.name)
            self.assertIn("CC0", b["items"][0]["credit"])
            self.assertIsNone(photo_view.block(dp, "site"))
            self.assertIn("data:image/jpeg;base64,", report_html.block(b))


if __name__ == "__main__":
    unittest.main()
