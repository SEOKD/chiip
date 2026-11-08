"""사건 인뎁스 관문 (마스터 지시 2026-11-08 — Industry Indepth 작업에 사건·분기 결산 통합)"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "industry"))
import event_gate as G  # noqa: E402

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 10, 7, 0, tzinfo=KST)
GS = {"hdd": ("HDD", {"co-wdc", "co-seagate"}), "utility": ("전력 유틸리티", {"co-duk", "co-so"})}


def al(level, ents, hours, doc="기사"):
    return {"level": level, "entities": ents, "sent_at": (NOW - timedelta(hours=hours)).isoformat(), "doc_type": doc, "title": "t"}


class TestGate(unittest.TestCase):
    def setUp(self):
        self._s = G.STATE
        G.STATE = Path(tempfile.mkdtemp()) / "g.json"

    def tearDown(self):
        G.STATE = self._s

    def test_rules(self):
        alerts = {"1": al("P1", ["co-wdc"], 5), "2": al("P1", ["co-seagate"], 10), "3": al("P1", ["co-duk"], 3)}
        r = G.check(NOW, alerts, GS, G.DEFAULT)
        self.assertEqual([c["industry"] for c in r["candidates"]], ["hdd"])   # 같은 묶음 2곳 동시
        alerts["4"] = al("P1", ["co-so"], 2, "규제·정책")
        self.assertIn("utility", [c["industry"] for c in G.check(NOW, alerts, GS, G.DEFAULT)["candidates"]])

    def test_window_and_cooldown(self):
        alerts = {"1": al("P0", ["co-wdc"], 72)}
        self.assertFalse(G.check(NOW, alerts, GS, G.DEFAULT)["due"])   # 48시간 밖
        alerts = {"1": al("P0", ["co-wdc"], 2)}
        G.done("hdd", NOW - timedelta(days=3))
        self.assertFalse(G.check(NOW, alerts, GS, G.DEFAULT)["due"])   # 14일 안 재알림 없음


if __name__ == "__main__":
    unittest.main()
