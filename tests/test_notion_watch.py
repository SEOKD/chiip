"""노션 실시간 감시(마스터 지시 2026-10-28) 오프라인 테스트 — 상태 판정·감지·마크다운 변환"""
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts"))

import notion_state as ns  # noqa: E402
import notion_watch as nw  # noqa: E402
import notion_write  # noqa: E402


class TestState(unittest.TestCase):
    def test_new_changed_skip_baseline(self):
        st = {"pages": {}}
        self.assertEqual(ns.decide("informations", "a-1", "법안", "2026-10-28T05:00:00Z", st), "NEW")
        self.assertEqual(ns.decide("informations", "a-1", "법안", "2026-10-28T05:00:00Z", st), "NEW")   # 처리 전이면 계속 NEW
        ns.mark("a-1", "2026-10-28T05:00:00Z", "r.md", st)
        self.assertEqual(ns.decide("informations", "a-1", "법안", "2026-10-28T05:00:00Z", st), "SKIP")
        self.assertEqual(ns.decide("informations", "a-1", "법안", "2026-10-28T09:00:00Z", st), "CHANGED")
        ns.baseline("stocks", "b-2", "삼성전자 005930", None, st)
        self.assertEqual(ns.decide("stocks", "b-2", "삼성전자 005930", "2026-10-28T01:00:00Z", st), "SKIP")    # 기준선 첫 관측
        self.assertEqual(ns.decide("stocks", "b-2", "삼성전자 005930", "2026-10-29T01:00:00Z", st), "CHANGED")
        self.assertEqual(ns.decide("insights", "c-3", "치입 검토 2026-10-28", None, st), "SKIP")


class TestDetect(unittest.TestCase):
    def test_settle_and_queue(self):
        now = datetime(2026, 10, 28, 13, 0, tzinfo=timezone.utc)
        pages = {"insights": {"id": "I"}, "informations": {"id": "N"}, "stocks": {"id": "S"}}

        def fake_list(root, depth, tok=None):
            if root == "N":
                yield "p-old", "오래된 정보", "2026-10-28T12:00:00Z", ""
                yield "p-fresh", "쓰는 중", "2026-10-28T12:55:00Z", ""   # 5분 전 → 다음 회차
            return
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(ns, "STATE", Path(d) / "s.json"), \
                mock.patch.object(nw, "QUEUE", Path(d) / "q.json"), \
                mock.patch.object(nw, "cfg", return_value={"pages": pages}), \
                mock.patch.object(nw, "list_pages", side_effect=fake_list):
            found = nw.detect("tok", now=now, dry=True)
        self.assertEqual([j["page_id"] for j in found], ["p-old"])
        self.assertEqual(found[0]["role"], "informations")


class TestMarkdown(unittest.TestCase):
    def test_blocks(self):
        md = "# 제목\n\n문단 첫 줄\n이어지는 줄\n\n- 항목\n> 인용\n| a | b |\n|---|---|\n| 1 | 2 |"
        b = notion_write.md_blocks(md)
        types = [x["type"] for x in b]
        self.assertEqual(types[0], "heading_1")
        self.assertIn("bulleted_list_item", types)
        self.assertIn("quote", types)
        para = [x for x in b if x["type"] == "paragraph"]
        self.assertEqual(para[0]["paragraph"]["rich_text"][0]["text"]["content"], "문단 첫 줄 이어지는 줄")
        long = notion_write._rt("가" * 4500)
        self.assertEqual(len(long), 3)          # 2000자 조각


class TestXlsx(unittest.TestCase):
    def test_xlsx_text(self):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                       '<si><t>Bill</t></si><si><t>Status</t></si></sst>')
            z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                       '<sheetData><row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row><row><c><v>0.5</v></c></row></sheetData></worksheet>')
        text = nw.xlsx_text(buf.getvalue())
        self.assertIn("Bill | Status", text)
        self.assertIn("0.5", text)


if __name__ == "__main__":
    unittest.main()
