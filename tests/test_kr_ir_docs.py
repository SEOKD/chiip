"""한국 IR 자료 감시 시험 — 분류·기간·IRGO 목록·공식 자료실·알림 범위(2026-10-30)"""
import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))

from pollers import kr_ir_docs as k  # noqa: E402

IRGO = """
<li class="clearfix ir_information " data-href="https://m.irgo.co.kr/IR자료/77221/TB/두산에너빌리티-2026년-3분기-경영실적">
  <div class="flr dataInfo"><h3 class="font_big ellipsis">두산에너빌리티, 2026년 3분기 경영실적</h3>
  <!-- <p> [A034020]두산에너빌리티_20261029.pdf&nbsp;본 내용은 </p> --><em>두산에너빌리티 I 1일전</em></div></li>
<li class="clearfix ir_information " data-href="https://m.irgo.co.kr/IR자료/77242/TB/두산에너빌리티-삼성증권-NDR">
  <h3>두산에너빌리티, 삼성증권 NDR</h3></li>
<li class="clearfix " data-href="https://m.irgo.co.kr/IR자료/77064/TB/ISC-ISC--3Q-실적발표-컨퍼런스콜-주요-내용-요약-"><span>2일전</span></li>
<li class="clearfix " data-href="https://m.irgo.co.kr/IR자료/77064/TB/ISC-ISC--3Q-실적발표-컨퍼런스콜-주요-내용-요약-"><span>2일전</span></li>
"""
TODAY = date(2026, 10, 30)


class TestParse(unittest.TestCase):
    def test_periods(self):
        for s, want in (("2026년 3분기 경영실적", "FY2026Q3"), ("2026년도 3분기", "FY2026Q3"), ("3Q26 Earnings", "FY2026Q3"), ("2026_3Q_conference_kor.pdf", "FY2026Q3"),
                        ("Q3 2026 results", "FY2026Q3"), ("26년 2분기", "FY2026Q2"), ("2025년 연간 경영실적", "FY2025Q4"), ("회사 소개", None)):
            self.assertEqual(k.period_of(s, ""), want, s)
        self.assertEqual(k.bare_period("3Q 실적발표", date(2026, 10, 28)), "FY2026Q3")
        self.assertEqual(k.bare_period("4Q 실적", date(2027, 2, 1)), "FY2026Q4")

    def test_kinds(self):
        self.assertEqual(k.kind_of("2026년 3분기 경영실적", ""), "presentation")
        self.assertEqual(k.kind_of("", "https://x/2026_3Q_conference_kor.pdf"), "presentation")
        self.assertEqual(k.kind_of("3Q 실적발표 컨퍼런스콜 주요 내용 요약", ""), "transcript")
        self.assertEqual(k.kind_of("2026 3Q Script", ""), "transcript")
        self.assertEqual(k.kind_of("경영실적 설명 및 Q&A", ""), "qa")
        self.assertEqual(k.kind_of("3분기 실적 다시보기", ""), "video")
        for s in ("삼성증권 NDR", "분기보고서", "주주총회 소집", "2026 Asia-Pacific Conference 참석", "CEO Presentations"):
            self.assertIsNone(k.kind_of(s, ""), s)

    def test_irgo_list(self):
        docs = k.scan_irgo(IRGO, TODAY)
        self.assertEqual([d["key"] for d in docs], ["irgo:77221", "irgo:77064"])
        self.assertEqual((docs[0]["date"], docs[0]["period"], docs[0]["kind"]), ("2026-10-29", "FY2026Q3", "presentation"))
        self.assertEqual((docs[1]["date"], docs[1]["period"], docs[1]["kind"]), ("2026-10-28", "FY2026Q3", "transcript"))
        self.assertTrue(docs[1]["title"].startswith("ISC ISC 3Q"))   # 제목이 없는 글은 주소 글자로

    def test_official_page_and_pdf_only(self):
        html = """<a href="//images.samsung.com/kdp/ir/events/2026/2026_3Q_conference_kor.pdf">Download PDF</a>
                  <a href="/ir/menu.html">실적 발표 자료</a> <script>var u="//images.samsung.com/kdp/ir/events/2026/2026_2Q_conference_kor.pdf";</script>"""
        docs = k.scan_page(html, "https://www.samsung.com/sec/ir/")
        self.assertEqual([d["period"] for d in docs], ["FY2026Q3", "FY2026Q2"])
        self.assertTrue(all(d["url"].startswith("https://images.samsung.com/") for d in docs))


def doc(num, period, kind="presentation", d="2026-10-29"):
    return {"url": f"https://m.irgo.co.kr/IR자료/{num}/x", "key": f"irgo:{num}", "title": f"회사, {period}", "kind": kind, "date": d, "period": period}


class TestPoll(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = {}
        self.docs = []
        cfg = {"companies": {"co-a": {"name": "에이", "code": "000001"}}}
        self.now = datetime(2026, 10, 30, 12, 0)
        self.p = [patch.object(k.common, "load_yaml", lambda p: cfg),
                  patch.object(k.common, "load_state", lambda n, d=None: json.loads(json.dumps(self.state)) if n == k.STATE and self.state else (d if d is not None else {})),
                  patch.object(k.common, "save_state", lambda n, d: self.state.update(json.loads(json.dumps(d)))),
                  patch.object(k.common, "now_kst", lambda: self.now),
                  patch.object(k, "CACHE", Path(self.tmp.name)),
                  patch.object(k, "company_docs", lambda c: (self.docs, 1)),
                  patch.object(k, "hot_ids", lambda s, n, h: {"co-a"}),
                  patch.object(k, "content_of", lambda d: (d["url"] + ".pdf", "본문", b"%PDF-1.5")),
                  patch.object(k, "save_pdf", lambda cid, d, raw: "radar/inbox/kr_ir/x.pdf"),
                  patch.object(k, "save_text", lambda cid, d, u, t: f"radar/inbox/kr_ir/{d['key']}.txt"),
                  patch.object(k.common, "make_item", lambda src, uid, url, title, pub, typ, lang, sn, extra=None: {"source_id": src, "title": title, "url": url, **(extra or {})})]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def test_first_run_alerts_only_recent(self):
        self.docs = [doc(3, "FY2026Q3"), doc(2, "FY2026Q2", d="2026-07-30"), doc(1, "FY2026Q1", d="2026-04-30")]
        items = k.poll(only=["co-a"])
        self.assertEqual([i["period"] for i in items], ["FY2026Q3"])
        self.assertEqual(items[0]["prev_period"], "FY2026Q2")   # 직전 기간 자료를 함께 받는다
        self.assertEqual(items[0]["source_id"], k.SRC)
        self.assertEqual(items[0]["local_pdf"], "radar/inbox/kr_ir/x.pdf")   # 글자가 적은 PDF는 원본을 남긴다
        self.assertEqual(k.poll(only=["co-a"]), [])              # 두 번째는 새 자료가 없다

    def test_script_goes_to_qa_source(self):
        k.poll(only=["co-a"])
        self.docs = [doc(9, "FY2026Q3", "transcript")]
        items = k.poll(only=["co-a"])
        self.assertEqual((items[0]["source_id"], items[0]["source_class"]), (k.SRC_QA, "IR 질의응답"))

    def test_old_document_is_not_alerted_after_baseline(self):
        k.poll(only=["co-a"])
        self.docs = [doc(8, "FY2024Q1", d="2024-05-01")]
        self.assertEqual(k.poll(only=["co-a"]), [])

    def test_failed_download_is_retried_next_run(self):
        k.poll(only=["co-a"])
        self.docs = [doc(7, "FY2026Q3")]
        with patch.object(k, "content_of", side_effect=OSError("x")):
            self.assertEqual(k.poll(only=["co-a"]), [])
        self.assertEqual(len(k.poll(only=["co-a"])), 1)

    def test_one_company_failure_does_not_stop_poll(self):
        with patch.object(k, "company_docs", side_effect=OSError("x")):
            self.assertEqual(k.poll(only=["co-a"]), [])


class TestPtPair(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache = self.root / "kr"
        self.cache.mkdir()
        self.fetched = []
        cfg = {"companies": {"co-a": {"name": "에이", "code": "000001"}}}
        self.p = [patch.object(k.common, "load_yaml", lambda p: cfg), patch.object(k.common, "ROOT", self.root), patch.object(k, "CACHE", self.cache)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.tmp.cleanup()

    def test_returns_this_and_prior_quarter_saved(self):
        for per in ("FY2026Q1", "FY2026Q2", "FY2026Q3"):
            (self.cache / f"co-a_presentation_{per}_abc.txt").write_text("x", encoding="utf-8")
        with patch.object(k, "company_docs", side_effect=AssertionError("이미 둘 있으면 받지 않는다")):
            got = k.pt_pair("000001")   # 종목코드로도 찾는다
        self.assertEqual([x["period"] for x in got], ["FY2026Q3", "FY2026Q2"])
        self.assertTrue(got[0]["text"].endswith("FY2026Q3_abc.txt"))

    def test_downloads_missing_prior_quarter(self):
        (self.cache / "co-a_presentation_FY2026Q3_abc.txt").write_text("x", encoding="utf-8")
        docs = [doc(3, "FY2026Q3"), doc(2, "FY2026Q2", d="2026-07-30"), doc(1, "FY2026Q1", d="2026-04-30")]

        def content(d):
            self.fetched.append(d["period"])
            return d["url"], "본문" * 2000, b"%PDF-1.5"
        with patch.object(k, "company_docs", lambda c: (docs, 1)), patch.object(k, "content_of", content):
            got = k.pt_pair("co-a")
        self.assertEqual(self.fetched, ["FY2026Q2"])
        self.assertEqual([x["period"] for x in got], ["FY2026Q3", "FY2026Q2"])
        self.assertIsNone(got[1]["pdf"])   # 글자가 충분한 PDF는 원본을 남기지 않는다

    def test_unknown_company(self):
        with self.assertRaises(ValueError):
            k.pt_pair("co-z")


class TestPulseWiring(unittest.TestCase):
    def test_classes(self):
        import pulse
        self.assertEqual(pulse.class_of("src-kr-ir-docs"), "IR 자료")
        self.assertEqual(pulse.class_of("src-kr-ir-qa"), "IR 질의응답")
        self.assertTrue(pulse.relevant({"title": "삼성전자 3분기", "language": "ko"}, "IR 자료"))


if __name__ == "__main__":
    unittest.main()
