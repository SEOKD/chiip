"""기사 소재 — 한국 전자기업 공급망 상대방 판별(마스터 지시 2026-11-09)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "article"))
import pitch_pool as P  # noqa: E402


class TestCounterparty(unittest.TestCase):
    def test_names_and_ids(self):
        self.assertEqual(P.counterparty("Advantest IR: 決算説明会資料 FY2026Q2", [])[0], "Advantest")
        self.assertIn("SK하이닉스", P.counterparty("", ["co-nvidia"])[1])
        self.assertIsNone(P.counterparty("Legrand IR: 실적 발표 자료", ["co-legrand"]))
        self.assertIsNone(P.counterparty("Armory results", []))          # 'Arm'이 단어 안에 든 경우는 아니다


if __name__ == "__main__":
    unittest.main()
