"""노션 첨부 토큰 경로 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import notion_library as nl  # noqa: E402

PAGE = {"results": [{"id": "b1", "type": "pdf", "pdf": {"type": "file", "file": {"url": "https://s3/x/GS_-_NVT_beat.pdf?sig"}, "name": "GS_-_NVT_beat.pdf"}},
                    {"id": "b2", "type": "paragraph", "paragraph": {}}], "has_more": False}
CFG = {"roots": [{"name": "IB Report", "id": "p1"}], "kinds": ["pdf", "xlsx"], "classes": [{"name": "IB 리포트", "match": ["IB Report"], "license": True}], "default_class": "일반 자료"}


class TestPull(unittest.TestCase):
    def test_indexes_and_downloads_new_files(self):
        with mock.patch.object(nl, "api_get", return_value=PAGE), mock.patch.object(nl, "put", return_value=(1, [])) as put:
            new, done, failed = nl.pull("t", [], CFG, [], "2026-11-04")
        self.assertEqual([r["id"] for r in new], ["b1"])
        self.assertEqual(new[0]["cls"], "IB 리포트")
        self.assertEqual(done, 1)
        self.assertEqual(put.call_args[0][0]["files"][0]["url"], "https://s3/x/GS_-_NVT_beat.pdf?sig")

    def test_no_token_skips(self):
        with mock.patch.object(nl.common, "load_env", return_value={}):
            self.assertIn("없음", nl.run())


if __name__ == "__main__":
    unittest.main()
