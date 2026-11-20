"""일반 단어와 겹치는 회사 이름 오매칭 방지(2026-11-20 마스터 지시 "Community Unity Bank에 Unity가 적혀 있다고 이걸 가져오면 어떻게 하나?")"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar" / "pollers"))
sys.path.insert(0, str(ROOT / "radar"))
import common  # noqa: E402
import fulltext  # noqa: E402


class TestAmbiguous(unittest.TestCase):
    def test_unity_bank_not_unity_software(self):
        self.assertNotIn("us-u", common.match_entities("OakNorth Secures U.S. Federal Reserve Clearance to Buy Community Unity Bank - WSJ"))

    def test_unity_with_context(self):
        self.assertIn("us-u", common.match_entities("Unity shares jump as game engine revenue beats"))
        self.assertIn("us-u", common.match_entities("Unity Software raises outlook"))   # 전체 이름은 문맥 없이도

    def test_carrier(self):
        self.assertNotIn("us-carr", common.match_entities("Navy sends aircraft carrier to Pacific"))
        self.assertIn("us-carr", common.match_entities("Carrier raises HVAC outlook"))


class TestWireTicker(unittest.TestCase):
    def test_single_letter_ticker_needs_exchange(self):
        with tempfile.TemporaryDirectory() as d:
            day = Path(d) / common.now_kst().strftime("%Y%m%d")
            day.mkdir()
            prefix = fulltext.WIRE_PREFIX if isinstance(fulltext.WIRE_PREFIX, str) else fulltext.WIRE_PREFIX[0]
            (day / f"{prefix}a.json").write_text(json.dumps({"title": "Canadian Solar e-STORAGE deal", "snippet": "projects in Texas, U.S. and Australia"}), encoding="utf-8")
            (day / f"{prefix}b.json").write_text(json.dumps({"title": "Unity reports results", "snippet": "Unity Software Inc. (NYSE: U) today"}), encoding="utf-8")
            with mock.patch.object(fulltext.common, "INBOX", Path(d)):
                got = fulltext.wire_candidates({"title": "Some news", "entities_matched": ["us-u"]})
        self.assertEqual([g["title"] for g in got], ["Unity reports results"])


if __name__ == "__main__":
    unittest.main()
