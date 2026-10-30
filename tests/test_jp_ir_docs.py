"""일본 IR 자료실 상시 감시 시험 (마스터 지시 2026-10-30 — 일본 기업은 PT 자료·Q&A 스크립트를 실적 보도자료 뒤에 늦게 낸다)"""
import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))

from pollers import common, jp_ir_docs as d, jp_ir_qa  # noqa: E402
import pulse  # noqa: E402

IBIDEN = """<a href="/ir/library/presentation/index.html">最新の決算概要について知りたい</a>
<a href="/ir/items/QA_FY25Q4.pdf">2025年度決算説明会主な質疑応答(2026年5月12日）（PDF：767KB）</a>
<a href="/ir/items/kessannsetsumei2026Q2.pdf">2026年度第2四半期決算説明会資料(2026年10月30日）（PDF：2,116KB）</a>
<a href="/ir/items/QA_FY2026Q1.pdf">2026年度第1四半期決算主な質疑応答（PDF：821KB）</a>
<a href="/ir/items/kessannsetsumei2026Q1.pdf">2026年度第1四半期決算説明会資料(2026年8月5日）（PDF：1,023KB）</a>
<a href="/ir/faq/">よくあるご質問</a>"""
MURATA = """<a href="https://corporate.murata.com/-/media/irnews/2026/1030b/26q2-j-speach.ashx?la=ja-jp&amp;cvid=20261030011256000000">2026年度 第2四半期 決算説明会資料 (PDF: 2.23MB)</a>
<a href="https://corporate.murata.com/-/media/irnews/2026/0731d/26q1-j-speach.ashx?la=ja-jp&amp;cvid=20260804062651000000">2026年度 第1四半期 決算説明会資料 (PDF: 862KB)</a>
<a href="https://corporate.murata.com/-/media/irnews/2026/0731d/26q1-j.ashx?la=ja-jp&amp;cvid=20260806080632000000">2026年度 第1四半期 決算説明会書き起こし(説明･Q&amp;A) (PDF: 3.00MB)</a>
<a href="/ja-jp/ir/library/video/results20260731">2026年度 第1四半期 決算説明会動画配信(説明･Q&amp;A)</a>"""


class TestParse(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(d.kind_of("2026年度 第1四半期 決算説明会書き起こし(説明･Q&A)", "x.ashx"), "transcript")   # Q&A가 들어 있어도 전문
        self.assertEqual(d.kind_of("決算説明会動画配信(説明･Q&A)", "/video/results20260731"), "video")
        self.assertEqual(d.kind_of("2026年度第1四半期決算主な質疑応答", "QA_FY2026Q1.pdf"), "qa")
        self.assertEqual(d.kind_of("2027年3月期 第2四半期 (PDF: 298KB)", "26q2-j-fls.ashx"), "tanshin")
        self.assertIsNone(d.kind_of("よくあるご質問", "/ir/faq/"))

    def test_period_japanese_fiscal_year(self):
        self.assertEqual(d.period_of("2027年3月期 第2四半期", ""), "FY2026Q2")   # 3월 결산 → 年度 기준
        self.assertEqual(d.period_of("2026年度第2四半期決算説明会資料", ""), "FY2026Q2")
        self.assertEqual(d.period_of("2025年度決算説明会資料", ""), "FY2025Q4")
        self.assertEqual(d.period_of("2025年度中間決算説明会主な質疑応答", ""), "FY2025Q2")
        self.assertEqual(d.period_of("資料", "https://x/26q1-j-speach.ashx"), "FY2026Q1")
        self.assertEqual(d.period_of("資料", "https://x/kessannsetsumei2026Q2.pdf"), "FY2026Q2")
        self.assertEqual(d.period_of("決算短信", "https://x/J_FR_FY2026_1Q.pdf"), "FY2026Q1")   # 4분기로 잘못 읽던 형식

    def test_dates_and_norm(self):
        self.assertEqual(d.doc_date("決算説明会資料(2026年10月30日）", ""), date(2026, 10, 30))
        self.assertEqual(d.doc_date("決算説明会資料", "https://x/irnews/2026/1030b/26q2.ashx"), date(2026, 10, 30))
        a = d.norm_url("https://x/a.ashx?la=ja-jp&cvid=1"); b = d.norm_url("https://x/a.ashx?la=ja-jp&cvid=2")
        self.assertEqual(a, b)
        self.assertIn("la=ja-jp", a)

    def test_scan_skips_menu_links(self):
        docs = d.scan_docs(IBIDEN, "https://www.ibiden.co.jp/ir/library/presentation/index.html")
        self.assertEqual([x["kind"] for x in docs], ["qa", "presentation", "qa", "presentation"])   # '最新の決算概要' 메뉴·FAQ 제외
        self.assertEqual(docs[1]["period"], "FY2026Q2")

    def test_fresh(self):
        doc = {"date": "", "period": "FY2026Q2"}
        self.assertTrue(d.is_fresh(doc, "FY2026Q2", date(2026, 10, 31), 21))
        self.assertFalse(d.is_fresh({"date": "2017-04-28", "period": "FY2016Q4"}, "FY2026Q2", date(2026, 10, 31), 21))   # 옛 아카이브

    def test_pulse_class(self):
        self.assertEqual(pulse.class_of("src-jp-ir-docs"), "IR 자료")
        self.assertTrue(pulse.relevant({"title": "村田製作所 決算説明会資料", "language": "ja"}, "IR 자료"))


class TestPoll(unittest.TestCase):
    def run_poll(self, pages, states, today="2026-10-31T10:00:00+09:00"):
        cfg = {"companies": {"co-x": {"site": "https://x.co.jp", "doc_pages": list(pages)}}, "holidays": []}
        now = datetime.fromisoformat(today)
        with mock.patch.object(common, "load_yaml", side_effect=lambda p: cfg if "jp_ir" in p else {"companies": [{"id": "co-x", "ja": ["テスト"], "code": "9999", "en": "Test"}]}), \
             mock.patch.object(common, "load_state", side_effect=lambda n, default=None: states.setdefault(n, default if default is not None else {})), \
             mock.patch.object(common, "save_state", side_effect=lambda n, v: states.__setitem__(n, v)), \
             mock.patch.object(common, "now_kst", return_value=now), \
             mock.patch.object(common, "match_entities", return_value=[]), \
             mock.patch.object(common, "match_keywords", return_value=[]), \
             mock.patch.object(jp_ir_qa, "fetch", side_effect=lambda u, t=20: pages.get(u, b"%PDF-")), \
             mock.patch.object(jp_ir_qa, "to_text", return_value="本文"), \
             mock.patch.object(d, "save_text", return_value="radar/inbox/jp_ir/x.txt"), \
             mock.patch.object(d, "hot_ids", return_value=set()):
            return d.poll(only=["co-x"])

    def test_first_scan_sends_backlog_only(self):
        states = {}
        its = self.run_poll({"https://x.co.jp/ir/p.html": IBIDEN}, states)
        self.assertEqual([(i["source_id"], i["kind"], i["period"]) for i in its], [("src-jp-ir-docs", "presentation", "FY2026Q2")])
        self.assertTrue(its[0]["prev_url"].endswith("kessannsetsumei2026Q1.pdf"))   # 직전 기간 PT를 비교용으로
        exp = states["jp_ir_docs"]["companies"]["co-x"]["expect"]   # Q&A를 내 온 회사 → 같은 기간 Q&A 대기
        self.assertEqual(exp["period"], "FY2026Q2")
        self.assertEqual(self.run_poll({"https://x.co.jp/ir/p.html": IBIDEN}, states), [])   # 두 번째 회차엔 새것 없음

    def test_late_qa_clears_expect(self):
        states = {}
        self.run_poll({"https://x.co.jp/ir/p.html": IBIDEN}, states)
        later = IBIDEN + '\n<a href="/ir/items/QA_FY2026Q2.pdf">2026年度第2四半期決算主な質疑応答（PDF：800KB）</a>'
        its = self.run_poll({"https://x.co.jp/ir/p.html": later}, states, "2026-11-05T10:00:00+09:00")
        self.assertEqual([(i["source_id"], i["kind"]) for i in its], [("src-jp-ir-qa", "qa")])   # 펄스 ⑥ IR 질의응답으로
        self.assertNotIn("expect", states["jp_ir_docs"]["companies"]["co-x"])
        self.assertEqual(states["jp_ir_profile"]["co-x"]["lag_days"], 5)
        self.assertIn("https://x.co.jp/ir/items/QA_FY2026Q2.pdf", states["jp_ir_qa"]["companies"]["co-x"]["seen"])   # jp_ir_qa가 다시 안 보내게

    def test_missing_qa_falls_back_to_directive_b(self):
        states = {}
        self.run_poll({"https://x.co.jp/ir/p.html": IBIDEN}, states)
        its = self.run_poll({"https://x.co.jp/ir/p.html": IBIDEN}, states, "2026-11-12T10:00:00+09:00")
        self.assertEqual(len(its), 1)
        self.assertTrue(its[0]["fallback"])

    def test_murata_transcript_and_video(self):
        states = {}
        its = self.run_poll({"https://corporate.murata.com/ja-jp/ir/library/meetings": MURATA}, states)
        self.assertEqual([i["kind"] for i in its], ["presentation"])   # 영상은 기록만
        self.assertTrue(states["jp_ir_docs"]["companies"]["co-x"].get("video"))


if __name__ == "__main__":
    unittest.main()
