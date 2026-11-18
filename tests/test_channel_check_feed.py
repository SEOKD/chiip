"""Memory Channel Check 전건 해설(마스터 지시 2026-11-18)"""
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import channel_check_feed as F  # noqa: E402
import notion_library as NL  # noqa: E402


def row(i, added, cls="채널체크", status="text"):
    return {"id": i, "name": f"{i}.pdf", "cls": cls, "added": added, "status": status, "chars": "100", "broker": "", "doc_date": ""}


class TestChannelCheck(unittest.TestCase):
    def test_all_new_pdfs_no_selection(self):
        rows = [row("old", "2026-11-04"), row("a", "2026-11-18"), row("b", "2026-11-18"), row("ib", "2026-11-18", cls="IB 리포트"),
                row("c", "2026-11-18", status="new")]
        c, waiting, st = F.candidates(rows, st={}, today=date(2026, 11, 18))
        self.assertEqual([x["id"] for x in c], ["a", "b"])        # 기준선·IB 제외, 고르지 않고 전부
        self.assertEqual([x["id"] for x in waiting], ["c"])       # 텍스트 대기
        self.assertEqual(st["baseline"], ["old"])

    def test_check_gate(self):
        p = {"id": "a", "summary": "s", "claims": ["x"] * 3, "numbers": ["1", "2"], "korea": "k", "weak": "w", "next": "n"}
        self.assertEqual(F.check(p, rows=[row("a", "2026-11-18")]), [])
        self.assertTrue(F.check({**p, "claims": ["x"]}, rows=[]))
        self.assertTrue(F.check({**p, "summary": "비중 확대"}, rows=[]))

    def test_classify_by_subpage(self):
        cfg = NL.config()
        self.assertEqual(NL.classify("Informations / Memory Channel Check", cfg), "채널체크")
        self.assertIn("채널체크", cfg["blocked_classes"])


if __name__ == "__main__":
    unittest.main()


class TestIbDigestMacro(unittest.TestCase):
    def test_macro_names(self):
        import ib_digest_feed as D
        for n in ("GS - 2027 Global Rates Outlook", "GS - 2027 Global FX Outlook - Timing the Turn.pdf", "MS - US Economics Outlook",
                  "Citi - Global Macro Strategy", "CTA_Report_20261117.pdf", "MS - Iron Ore Chartbook"):
            self.assertTrue(D.is_macro(n), n)
        for n in ("Bernstein - US Semis - Intel and AMD", "MS - SpaceX (SPCX) - SpaceX Economics, 10 Takeaways.pdf",
                  "Bernstein - China Semicap - HBM Shortage Drives More DRAM Capex.pdf", "Citi - Hesai (HSAI.US)"):
            self.assertFalse(D.is_macro(n), n)
