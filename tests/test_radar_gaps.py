"""레이더 누락 보완 (마스터 지시 2026-11-08 — 닛토보 결산·증설, AT&S PT)"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
sys.path.insert(0, str(ROOT / "scripts" / "valuation" / "v2"))
sys.path.insert(0, str(ROOT / "scripts" / "alpha"))
import promote  # noqa: E402
import fiscal_ir_docs as fd  # noqa: E402
import alpha_watch as aw  # noqa: E402
from pollers import common, gate  # noqa: E402

KST = timezone(timedelta(hours=9))


def jp(title):
    return {"source_id": "src-jp-disclosure", "title": title, "entities_matched": ["co-nittobo"], "doc_type": "기사", "url": "", "item_id": "x:" + title}


class TestPromoteRecord(unittest.TestCase):
    def setUp(self):
        self._ls, self._ss = common.load_state, common.save_state
        self.mem = {}
        common.load_state = lambda n, d=None: json.loads(json.dumps(self.mem.get(n, d if d is not None else {})))
        common.save_state = lambda n, v: self.mem.__setitem__(n, json.loads(json.dumps(v)))

    def tearDown(self):
        common.load_state, common.save_state = self._ls, self._ss

    def test_peek_does_not_burn_signature(self):
        derived = jp("【決算速報】日東紡、２７年３月期第２四半期決算は増益(フィスコ)")
        primary = jp("日東紡[3110]：2027年３月期 第２四半期（中間期）決算短信〔日本基準〕(連結) (適時開示)")
        self.assertTrue(promote.check(derived, record=False))
        self.assertTrue(promote.check(primary, record=False))   # 예전엔 파생 기사가 서명을 태워 원문이 None
        promote.commit(primary)
        self.assertIsNone(promote.check(primary, record=False))

    def test_capex_words(self):
        hit = promote.match(jp("日東紡、半導体用ガラス材料に200億円投資 29年度に生産能力3.6倍 - 日本経済新聞"))
        self.assertTrue(hit and hit[1].endswith(":capex"))


class TestFiscalIrDocs(unittest.TestCase):
    def test_universe_has_ats_and_skips_us(self):
        u = fd.universe()
        self.assertEqual(u.get("eu-ats"), "XWBO_ATS")
        self.assertFalse(any(str(k).startswith(("NYSE_", "XJPX_")) for k in u.values()))

    def test_put_keeps_fresh_only(self):
        tmp = Path(tempfile.mkdtemp())
        f = tmp / "o.json"
        f.write_text("log\n" + json.dumps([{"key": "XWBO_ATS", "docs": [
            {"role": "slide_deck", "id": "T-NEW", "date": "2026-11-05", "fy": 2027, "fq": 2},
            {"role": "slide_deck", "id": "T-OLD", "date": "2026-05-21", "fy": 2026, "fq": 4}]}]), encoding="utf-8")
        saved = []
        ls, ss, sn = common.load_state, common.save_state, common.save_new_items
        mem = {}
        common.load_state = lambda n, d=None: mem.get(n, d if d is not None else {})
        common.save_state = lambda n, v: mem.__setitem__(n, v)
        common.save_new_items = lambda items: saved.extend(items) or items
        try:
            n, logged = fd.put(f, now=datetime(2026, 11, 8, 12, tzinfo=KST))
        finally:
            common.load_state, common.save_state, common.save_new_items = ls, ss, sn
        self.assertEqual((n, logged), (1, 1))
        self.assertEqual(saved[0]["source_id"], "src-fiscal-ir-docs")
        self.assertEqual(saved[0]["entities_matched"], ["eu-ats"])
        self.assertIn("PT", saved[0]["title"])

    def test_gate_keeps_ir_docs(self):
        for sid in ("src-fiscal-ir-docs", "src-tw-hk-ir-docs"):
            self.assertTrue(gate.keep({"source_id": sid, "entities_matched": ["eu-ats"]}, focus=set()))


class TestQueuePriority(unittest.TestCase):
    def test_fresh_event_beats_older_higher_alpha(self):
        now = datetime(2026, 11, 8, 12, tzinfo=KST)
        old = {"id": "a", "added": "2026-10-28T21:00:00+09:00"}
        ev = {"id": "b", "added": "2026-11-05T20:00:00+09:00", "event_at": "2026-11-07T15:00:00+09:00"}
        alpha = {"a": 6.0, "b": 5.2}
        self.assertGreater(aw.priority(ev, alpha, now, {}), aw.priority(old, alpha, now, {}))


if __name__ == "__main__":
    unittest.main()
