"""Analysis 종목별 원천 관문 (마스터 지시 2026-11-08)"""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import gather  # noqa: E402

CFG = {"max_age_days": 3, "sources": [
    {"id": "tg_channels", "region": "all", "kind": "script"},
    {"id": "lobby", "region": "us", "kind": "script"},
    {"id": "kr_ir_pt", "region": "kr", "kind": "script"},
    {"id": "fiscal", "region": "all", "kind": "model"}]}
CO = {"id": "co-x", "ticker": "XYZ", "name": "엑스", "legal": "X Corp", "region": "us", "names": ["엑스", "X Corp"]}


class TestGate(unittest.TestCase):
    def _missing(self, sources, at=None):
        now = datetime(2026, 11, 8, 9, tzinfo=gather.KST)
        led = {"at": (at or now).isoformat(), "sources": sources}
        with mock.patch.object(gather, "load_ledger", return_value=led), mock.patch.object(gather, "company", return_value=CO):
            return gather.missing("co-x", CFG, now)

    def test_all_applicable_needed(self):
        m = self._missing({"tg_channels": {"status": "ok"}})
        self.assertEqual([x.split("(")[0] for x in m], ["lobby", "fiscal"])   # 한국 전용 원천은 미국 종목에 요구하지 않는다

    def test_failure_blocks_reason_passes(self):
        base = {"tg_channels": {"status": "ok"}, "fiscal": {"status": "ok"}}
        self.assertTrue(self._missing({**base, "lobby": {"status": "실패: 키 없음"}}))
        self.assertTrue(self._missing({**base, "lobby": {"status": "해당 없음"}}))           # 이유 없는 '해당 없음'은 안 된다
        self.assertEqual(self._missing({**base, "lobby": {"status": "해당 없음(LDA 키 없음, SEC·언론 확인)"}}), [])

    def test_stale_ledger(self):
        now = datetime(2026, 11, 8, 9, tzinfo=gather.KST)
        self.assertIn("장부", self._missing({}, at=now - timedelta(days=5))[0])

    def test_short_ticker_matches_by_name_only(self):
        co = {**CO, "ticker": "MU", "names": ["Micron"]}
        self.assertFalse(gather._hits("MU stock falls", co))
        self.assertTrue(gather._hits("Micron raises guidance", co))
        self.assertTrue(gather._hits("XYZ beats", CO))


if __name__ == "__main__":
    unittest.main()
