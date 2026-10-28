"""포커스 점수·수집 관문·노션 기록(§21.13) 오프라인 테스트"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "focus"))

from pollers import common, gate  # noqa: E402
import score  # noqa: E402


def item(doc_type, ents=(), title="t", publisher=None, iid="x:1"):
    it = {"item_id": iid, "doc_type": doc_type, "entities_matched": list(ents), "title": title, "url": "u",
          "content_hash": iid}
    if publisher:
        it["publisher"] = publisher
    return it


class TestGate(unittest.TestCase):
    def test_news_only_seven_outlets(self):
        self.assertTrue(gate.news_allowed(item("기사", title="Micron soars - Reuters")))
        self.assertFalse(gate.news_allowed(item("기사", title="SK하이닉스 실적 - 연합뉴스")))
        self.assertTrue(gate.news_allowed(item("공시")))

    def test_focus_rules(self):
        focus = {"co-micron"}
        self.assertTrue(gate.keep(item("공시", ["co-micron"]), focus))
        self.assertFalse(gate.keep(item("공시", ["co-ti"]), focus))
        self.assertFalse(gate.keep(item("보도자료"), focus))           # 종목 없는 보도자료는 버림
        self.assertTrue(gate.keep(item("규제·정책", ["co-ti"]), focus))  # 정책은 항상
        self.assertTrue(gate.keep(item("학회·협회"), focus))
        self.assertTrue(gate.keep(item("기사", title="HBM shortage - Bloomberg"), focus))
        self.assertTrue(gate.keep(item("공시", ["co-ti"]), None))      # 점수 없으면 관문 열림

    def test_mentions_counted_before_filter(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(common, "STATE", Path(d)):
            gate.count_mentions([item("기사", ["co-ti"], iid="a"), item("기사", ["co-ti"], iid="a"),
                                 item("공시", ["co-ti", "co-micron"], iid="b")])
            self.assertEqual(gate.mentions(1), {"co-ti": 2, "co-micron": 1})


class TestScore(unittest.TestCase):
    def test_quant_magnitude_and_missing(self):
        rows = [{"id": "a", "ret30": 0.3, "narrative_heat": 5, "rev_ntm_30": -0.2, "peer_premium": 0.5},
                {"id": "b", "ret30": 0.01, "narrative_heat": 0, "rev_ntm_30": 0.01, "peer_premium": 0.0},
                {"id": "c", "ret30": -0.25, "narrative_heat": 2, "rev_ntm_30": None, "peer_premium": -0.6}]
        q = score.quant_components(rows, {"a": 10, "b": 0, "c": 3})
        self.assertGreater(q["a"]["attention"], q["b"]["attention"])
        self.assertEqual(q["b"]["narrative"], 0.0)
        self.assertGreater(q["a"]["fundamental"], q["b"]["fundamental"])   # 하향 리비전도 '룸'이 큼
        self.assertGreater(q["c"]["multiple"], q["b"]["multiple"])        # 큰 디스카운트도 높음
        no_mention = score.quant_components([{**r, "ret30": None} for r in rows], {})
        self.assertIsNone(no_mention["a"]["attention"])                   # 언급·주가 모두 없으면 계산 안 함

    def test_combine_judgment_priority_delta_threshold(self):
        prepared = {"rows": [{"id": "a", "name": "A", "sub": "x", "attention": 4.0, "narrative": 6.0,
                              "fundamental": None, "multiple": None},
                             {"id": "b", "name": "B", "sub": "x", "attention": 9.0, "narrative": None,
                              "fundamental": None, "multiple": None}]}
        judg = {"a": {"fundamental": {"score": 8.0, "reason": "리비전 급상향"}, "attention": {"score": 6.0, "reason": ""}}}
        rows = {r["id"]: r for r in score.combine(prepared, judg, {"a": {"total": "5.5"}}, {"threshold": 5.0})}
        self.assertAlmostEqual(rows["a"]["total"], (6 + 6 + 8) / 3, places=2)
        self.assertAlmostEqual(rows["a"]["delta"], rows["a"]["total"] - 5.5, places=2)
        self.assertIn("attention=판단", rows["a"]["sources"])
        self.assertTrue(rows["a"]["focus"])
        self.assertIsNone(rows["b"]["total"])   # 요소 1개 → 미산정
        self.assertFalse(rows["b"]["focus"])

    def test_digest_marks_judgment(self):
        latest = {"day": "20261028", "prev_day": None, "threshold": 5.0, "focus": ["a"], "entered": [], "exited": [],
                  "unscored": [], "rows": [{"id": "a", "name": "A", "total": 6.0, "delta": None, "focus": True,
                                            "attention": 6.0, "narrative": 6.0, "fundamental": 6.0, "multiple": None,
                                            "sources": "attention=계산;narrative=계산;fundamental=판단"}]}
        text = score.digest(latest)
        self.assertIn("6.0판", text)
        self.assertIn("투자 권유가 아님", text)


class TestNotionAndButton(unittest.TestCase):
    def test_properties_and_queue(self):
        import notify
        import telegram_inbox as ti
        with tempfile.TemporaryDirectory() as d, mock.patch.object(common, "STATE", Path(d)), \
                mock.patch.object(ti, "QUEUE", Path(d) / "q.jsonl"):
            it = {"item_id": "src-sec-filings:0001", "title": "[SEC 8-K 실적] MICRON", "url": "https://sec/x",
                  "doc_type": "실적", "entities_matched": ["co-micron"], "published_at": "2026-10-28T06:00:00+09:00",
                  "source_id": "src-sec-filings"}
            ref = notify.remember_alert(it, "P1", "마이크론 실적 발표", "HBM 매출 상향(추정)")
            self.assertLessEqual(len(f"save:{ref}".encode()), 64)
            row = ti.enqueue(ref)
            ti.enqueue(ref, "가이던스 확인 필요")
            p = ti.notion_properties(ti.load_queue()[0])
            self.assertEqual(p["유형"]["select"]["name"], "공시·실적")
            self.assertEqual(p["종목"]["multi_select"][0]["name"], "Micron")
            self.assertEqual(p["날짜"]["date"]["start"], "2026-10-28")
            self.assertIn("가이던스", p["마스터 메모"]["rich_text"][0]["text"]["content"])
            self.assertEqual(len(ti.load_queue()), 1)
            self.assertEqual(row["level"], "P1")
            ti.mark_done({ref})
            self.assertEqual(ti.export_pending(), [])

    def test_button_payload(self):
        import notify
        sent = {}

        class R:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"ok": true}'

        def fake_open(url, data=None, timeout=20):
            sent["data"] = data.decode()
            return R()
        with mock.patch.object(common, "load_env", return_value={"TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"}), \
                mock.patch("urllib.request.urlopen", side_effect=fake_open), \
                mock.patch.object(notify, "_log"), mock.patch.object(common, "record_health"):
            self.assertTrue(notify.send("hi", "P1", ref="abc"))
        self.assertIn("save%3Aabc", sent["data"])


if __name__ == "__main__":
    unittest.main()
