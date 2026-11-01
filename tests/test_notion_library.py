"""노션 자료실 (마스터 지시 2026-11-01)"""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import notion_library as nl  # noqa: E402

COS = [{"id": "co-gevernova", "names": ["GE Vernova", "GEV"], "ticker": "GEV"}, {"id": "co-sk-hynix", "names": ["SK Hynix"], "ticker": "000660"}]
CFG = nl.config()
FETCH = '''{"title":"IB Report","text":"<file source=\\"notion-file-block://40bb5d1e-0998-8006-92e0-eb82439ff73e/d4bede5b-e446-4f8c-be43-a8d64a185eb0?space_id=97acc88c-3e6c-4c77-8017-69472b4d70cc&name=JPM_GE_Vernova_Power_SRA_2026-10-29_5510883.pdf\\" /> <file source=\\"notion-file-block://40bb5d1e-0998-8042-9627-e5adfbdd7262/e6a63e18-a48d-43e8-8072-da0426e0cbf4?space_id=x&name=photo.png\\" />"}'''


def row(**k):
    return {**{f: "" for f in nl.FIELDS}, "id": "a", "name": "x.pdf", "cls": "IB 리포트", "entities": "co-gevernova", "status": "text", **k}


class TestLibrary(unittest.TestCase):
    def test_sync_finds_attachments_and_metadata(self):
        new = nl.sync(FETCH, [], CFG, COS, "2026-11-01")
        self.assertEqual(len(new), 1)   # 그림은 뺀다
        r = new[0]
        self.assertEqual((r["cls"], r["broker"], r["doc_date"], r["entities"]), ("IB 리포트", "JPM", "2026-10-29", "co-gevernova"))

    def test_sync_is_idempotent(self):
        first = nl.sync(FETCH, [], CFG, COS, "2026-11-01")
        self.assertEqual(nl.sync(FETCH, first, CFG, COS, "2026-11-02"), [])

    def test_channel_check_is_never_served(self):
        self.assertEqual(nl.classify("Memory Channel Check", CFG), "채널체크")
        self.assertEqual(nl.usable([row(cls="채널체크")], "co-gevernova", CFG), [])

    def test_body_mentions_link_other_reports(self):
        self.assertEqual(nl.match("JPM_Sector_Power.pdf", "GE Vernova GE Vernova GE Vernova", COS), ["co-gevernova"])
        self.assertEqual(nl.match("JPM_Sector_Power.pdf", "GE Vernova once", COS), [])

    def test_short_tickers_do_not_match_filename_words(self):
        cos = [{"id": "x", "names": [], "ticker": "ON"}]
        self.assertEqual(nl.match("JPM_ON_Track.pdf", "", cos), [])

    def test_digest_rejects_copied_passages(self):
        hit = nl.shared_run("앞말 one two three four five six seven eight nine ten eleven twelve 뒷말", "x one two three four five six seven eight nine ten eleven twelve y", 12)
        self.assertTrue(hit)
        self.assertIsNone(nl.shared_run("the market sees orders falling near term", "orders fall in the near term says the market", 12))

    def test_unread_files_block_the_report(self):
        self.assertEqual(len(nl.unread([row()], "co-gevernova", CFG)), 1)
        self.assertEqual(nl.unread([row(status="digest")], "co-gevernova", CFG), [])
        self.assertEqual(nl.unread([row(cls="채널체크")], "co-gevernova", CFG), [])

    def test_related_mentions_do_not_block(self):
        r = row(entities="co-palantir", related="co-gevernova")
        self.assertEqual(len(nl.usable([r], "co-gevernova", CFG)), 1)
        self.assertEqual(nl.unread([r], "co-gevernova", CFG), [])

    def test_citations_use_digests_only(self):
        got = nl.citations([row(status="digest", broker="JPM", doc_date="2026-10-29"), row(id="b")], "co-gevernova", CFG)
        self.assertEqual(len(got), 1)
        self.assertIn("요지만", got[0])

    def test_xlsx_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "a.xlsx"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>매출</t></si></sst>')
                z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="s"><v>0</v></c><c><v>42</v></c></row></sheetData></worksheet>')
            self.assertIn("매출\t42", nl.xlsx_text(p))

    def test_ticker_resolves_to_id(self):
        self.assertEqual(nl.resolve("gev", COS), "co-gevernova")


if __name__ == "__main__":
    unittest.main()
