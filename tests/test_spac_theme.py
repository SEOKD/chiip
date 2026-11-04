"""SPAC 테마 판정·Pulse 연결 시험 (마스터 지시 2026-11-04)"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
from pollers import spac_theme as th  # noqa: E402
import pulse  # noqa: E402

C = th.cfg()


class T(unittest.TestCase):
    def test_space_word_alone_is_not_space_theme(self):
        self.assertEqual(th.classify_text("office space " * 20 + "bitcoin treasury", C)[0], None)

    def test_ai_needs_two_terms(self):
        self.assertIsNone(th.classify_text("silicon " * 10, C)[0])
        self.assertEqual(th.classify_text("GPU data center inference GPU data centers", C)[0], "AI·반도체")

    def test_single_term_theme(self):
        self.assertEqual(th.classify_text("humanoid robot " * 3 + "robot " * 6, C)[0], "로봇·자율")

    def test_target_name(self):
        _, _, t = th.classify_text("entered into a business combination agreement with Acme Photonics Inc. to", C)
        self.assertEqual(t, "Acme Photonics Inc.")

    def test_fetch_spac_waits_for_theme_and_skips_unmatched(self):
        root = Path(tempfile.mkdtemp())
        d = root / "knowledge" / "models" / "spac"
        d.mkdir(parents=True)
        today = pulse.common.now_kst().date().isoformat()
        with (d / "transitions.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["seen", "cik", "name", "tickers", "from", "to", "form", "filed", "url"])
            w.writerow([today, "1", "A Corp", "AAA", "S0", "S2", "425", today, "u1"])
            w.writerow([today, "3", "C Corp", "CCC", "S0", "S2", "425", today, "u3"])
            w.writerow([today, "2", "B Corp", "BBB", "S0", "S2", "425", today, "u2"])
        with (d / "themes.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, th.COLS)
            w.writeheader()
            w.writerow({"cik": "1", "spac": "A Corp", "target": "", "theme": "", "hits": 0, "terms": "", "doc": "", "at": ""})
            w.writerow({"cik": "3", "spac": "C Corp", "target": "Acme Inc.", "theme": "양자", "hits": 9, "terms": "quantum", "doc": "x", "at": ""})
        with mock.patch.object(pulse.common, "ROOT", root), mock.patch.object(pulse.common, "load_yaml", return_value={"alert_stages": ["S2", "S3", "S4", "S5"]}):
            st = {"spac_idx": 0}
            out = pulse.fetch_spac(st)
        self.assertEqual([x["ticker"] for x in out], ["CCC"])   # 1은 테마 없음 → 건너뜀, 3은 보냄
        self.assertEqual(st["spac_idx"], 2)                     # 2는 판정 대기 → 거기서 멈춤

if __name__ == "__main__":
    unittest.main()
