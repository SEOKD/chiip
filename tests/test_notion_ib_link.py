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


class TestMentionRank(unittest.TestCase):   # 본문 언급 연결·관련성 순(2026-11-12 마스터 지시)
    def test_body_mention_links_and_ranks_first(self):
        import notion_library as NL2
        cfg = {"blocked_classes": ["채널체크"], "mention_min": 5, "related_max_per_report": 2, "related_max_age_days": 45, "themes": []}
        rows = [{"id": i, "name": n, "cls": "IB 리포트", "entities": "", "related": "", "status": "text", "doc_date": d, "added": d, "chars": "1"}
                for i, n, d in (("a", "Macro_outlook.pdf", "2026-11-10"), ("b", "Old_note.pdf", "2026-11-01"), ("c", "Newest.pdf", "2026-11-11"))]
        NL2._MENT.clear()
        NL2._MENT.update({("a", "co-x"): 30, ("b", "co-x"): 6, ("c", "co-x"): 1})
        u = NL2.usable(rows, "co-x", cfg)
        self.assertEqual({r["id"] for r in u}, {"a", "b"})            # 1회 언급은 연결 안 함
        left = NL2.unread(rows, "co-x", cfg, today=__import__("datetime").date(2026, 11, 12))
        self.assertEqual([r["id"] for r in left], ["a", "b"])          # 최신(c)보다 언급 많은 순
        NL2._MENT.clear()


class TestIndustryWide(unittest.TestCase):   # 산업 리포트 연결 확대(2026-11-15 마스터 지시 "넓혀 줘")
    def test_digests_uncapped_new_capped_and_mentions(self):
        import notion_library as NL3
        from unittest import mock
        cfg = {"blocked_classes": ["채널체크"], "mention_min": 5, "related_max_per_report": 2, "related_max_age_days": 45, "themes": [], "industry_refs": {}}
        mk = lambda i, ent, st: {"id": i, "name": f"{i}.pdf", "cls": "IB 리포트", "entities": ent, "related": "", "status": st,
                                 "doc_date": "2026-11-12", "added": "2026-11-12", "chars": "1", "broker": "", "page": "", "kind": "", "reference": ""}
        rows = [mk(f"d{i}", "co-nvidia", "digest") for i in range(5)] + [mk(f"t{i}", "co-nvidia", "text") for i in range(4)] + [mk("body", "", "digest")]
        NL3._MENT.clear()
        with mock.patch.object(NL3, "config", return_value=cfg), mock.patch.object(NL3, "read", return_value=rows), \
             mock.patch.object(NL3, "mentions", side_effect=lambda r, m, cos=None: 9 if r["id"] == "body" else 0):
            todo, cites, use = NL3.industry_need("semiconductors.ai-accelerators", None, ("co-nvidia",), today=date(2026, 11, 15))
        ids = {r["id"] for r in use}
        self.assertTrue({f"d{i}" for i in range(5)} <= ids)       # 요지 있는 자료는 상한 없이
        self.assertEqual(len([r for r in use if r["status"] == "text"]), 2)   # 새로 요지를 쓸 것은 상한 2
        self.assertIn("body", ids)                                 # 본문에서 구성 종목을 다루는 자료
        self.assertEqual(len(todo), 2)
