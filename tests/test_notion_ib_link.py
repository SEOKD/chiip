"""IB 업종 리포트 연결·관련 자료 요지 의무 (마스터 지시 2026-11-08)"""
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import notion_library as NL  # noqa: E402

CFG = {"blocked_classes": ["채널체크"], "related_max_age_days": 45, "related_max_per_report": 2,
       "themes": [{"match": ["Utilities", r"\bPower\b"], "subs": ["Construction & Engineering"]}]}


def row(i, name, ent="", rel="", st="text", d="2026-11-01"):
    return {"id": i, "name": name, "cls": "IB 리포트", "entities": ent, "related": rel, "status": st, "doc_date": d, "added": d}


class TestLink(unittest.TestCase):
    def setUp(self):
        self._s = dict(NL._SUB)
        NL._SUB.clear()
        NL._SUB.update({"co-pwr": "Construction & Engineering", "co-nvda": "Semiconductors"})

    def tearDown(self):
        NL._SUB.clear()
        NL._SUB.update(self._s)

    def test_theme_report_reaches_sub_industry(self):
        rows = [row("a", "Americas_Utilities_Power_outlook.pdf")]
        self.assertEqual(len(NL.usable(rows, "co-pwr", CFG)), 1)
        self.assertEqual(len(NL.usable(rows, "co-nvda", CFG)), 0)

    def test_unread_primary_all_related_capped_and_recent(self):
        rows = [row("p", "x", ent="co-pwr"), row("r1", "Power a.pdf", d="2026-11-05"), row("r2", "Power b.pdf", d="2026-11-04"),
                row("r3", "Power c.pdf", d="2026-11-03"), row("old", "Power d.pdf", d="2026-08-01")]
        got = {r["id"] for r in NL.unread(rows, "co-pwr", CFG, today=date(2026, 11, 8))}
        self.assertEqual(got, {"p", "r1", "r2"})


if __name__ == "__main__":
    unittest.main()
