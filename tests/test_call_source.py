"""어닝콜 원천 단계(마스터 지시 2026-11-21) — Fiscal.ai → TradingView → 텔레그램 Fundeasyearnings"""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import call_source as cs  # noqa: E402

POSTS = [
    {"id": 100, "at": "2026-11-10T09:00:00+09:00", "url": "https://t.me/Fundeasyearnings/100",
     "text": "📊 AAON 실적발표 (2026년 3분기)\n세션: 장후\n📊 핵심 실적\nQ1: A(B사)·CEO\n- 질문: 수주?\n- 답변: 늘었다"},
    {"id": 101, "at": "2026-11-10T09:00:05+09:00", "text": "Q10: C(D사)·CFO\n- 질문: 마진?\n- 답변: 유지"},
    {"id": 102, "at": "2026-11-10T09:10:00+09:00", "text": "📊 POST 실적발표 (2026년 3분기)\n핵심 실적만"},
    {"id": 150, "at": "2026-11-10T10:00:00+09:00", "text": "Q2: 떨어진 글"},
]


class TestTelegram(unittest.TestCase):
    def test_threads_join_continuation(self):
        t = cs.threads(POSTS)
        self.assertEqual([(x["ticker"], x["has_qa"], len(x["ids"])) for x in t], [("AAON", True, 2), ("POST", False, 1)])
        self.assertIn("Q10:", t[0]["text"])

    def test_find_by_ticker_and_search_fallback(self):
        self.assertEqual(cs.tg_find("AAON", posts=POSTS)[0]["q"], 3)
        self.assertEqual(cs.tg_find("ZZZZ", posts=POSTS), [])
        with mock.patch.object(cs, "_search_posts", lambda tk, get=None: POSTS):
            self.assertEqual(cs.tg_find("AAON", posts=[], search=True)[0]["url"], "https://t.me/Fundeasyearnings/100")


class TestTv(unittest.TestCase):
    def test_pick_latest_call_doc(self):
        now = datetime(2026, 11, 21)
        data = {"items": [
            {"title": "Q3 2026 Earnings Call", "category": {"id": "call_transcript"}, "reported": datetime(2026, 11, 10).timestamp(),
             "views": [{"type": "transcript", "id": "T1"}, {"type": "summary", "id": "S1"}]},
            {"title": "Q2 2026 Earnings Call", "category": {"id": "call_transcript"}, "reported": datetime(2026, 8, 10).timestamp(), "views": [{"type": "summary", "id": "S0"}]},
            {"title": "10-Q", "category": {"id": "quarterly_report"}, "reported": datetime(2026, 11, 12).timestamp()}]}
        r = cs.tv_pick(data, now=now)
        self.assertEqual((r["kind"], r["transcript"], r["date"]), ("전문", "T1", "2026-11-10"))
        self.assertIsNone(cs.tv_pick({"items": []}, now=now))


class TestPut(unittest.TestCase):
    def test_put_writes_script_and_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "knowledge" / "models" / "companies" / "x"
            d.mkdir(parents=True)
            (d / "datapack.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(cs, "ROOT", Path(tmp)):
                cs.put("x", "telegram", "Q&A 정리", "2026-11-10", "https://t.me/Fundeasyearnings/100")
                dp = json.loads((d / "datapack.json").read_text(encoding="utf-8"))
                with self.assertRaises(SystemExit):
                    cs.put("x", "blog", "Q&A 정리", "2026-11-10", "u")
        self.assertEqual(dp["call"]["script"]["via"], "telegram")
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "valuation" / "v2"))
        import v2_to_report   # 한국 종목 관문은 via와 상관없이 call.script만 본다
        self.assertIsNone(v2_to_report.kr_call_gap({"ticker": "039030", **dp}))


class TestCompanyIr(unittest.TestCase):
    """⓪ 회사 공식 IR(2026-11-22 마스터 지시 — 일본·대만·홍콩·중국 공식 IR 1순위)"""
    def test_finds_latest_qa_for_entity_only(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            for day, name, ent, kind in (("20261120", "src-cn-ir-qa_aa01.json", ["cn-688126"], "transcript"),
                                         ("20261110", "src-tw-hk-ir-qa_bb02.json", "['co-tsmc']", "qa"),
                                         ("20261121", "src-cn-ir-docs_cc03.json", ["cn-688126"], "report"),
                                         ("20260601", "src-cn-ir-qa_dd04.json", ["cn-688126"], "transcript")):
                d = root / "radar" / "inbox" / day
                d.mkdir(parents=True, exist_ok=True)
                (d / name).write_text(json.dumps({"source_id": name.split("_")[0], "entities_matched": ent, "kind": kind, "doc_date": f"{day[:4]}-{day[4:6]}-{day[6:]}",
                                                  "url": "u", "title": "t", "grade": "A"}), encoding="utf-8")
            now = datetime(2026, 11, 22)
            got = cs.company_find("cn-688126", now=now, root=root)
            self.assertEqual([(g["date"], g["kind"]) for g in got], [("2026-11-20", "전문")])   # 자료(docs)와 120일 밖은 빼고
            self.assertEqual(cs.company_find("co-tsmc", now=now, root=root)[0]["kind"], "Q&A 정리")
            self.assertEqual(cs.company_find("co-tsm", now=now, root=root), [])   # 이름 일부만 같으면 아니다


if __name__ == "__main__":
    unittest.main()
