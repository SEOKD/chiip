"""특허 레이더 (마스터 지시 2026-11-08 — 한국 전자기업 특허 등록·특허 분쟁 데이터 파이프라인)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import patent_watch as P  # noqa: E402


class TestPatentWatch(unittest.TestCase):
    def setUp(self):
        self.comps = P.cfg()["companies"]

    def test_full_name_before_alias(self):
        self.assertEqual([n for _, n in P.who("월풀, 삼성전자 소송 정리 수순…LG전자엔 새 특허 공세", self.comps)], ["삼성전자", "LG전자"])
        self.assertEqual([n for _, n in P.who("HBM 장비 특허전…한미·한화 합의 가능할까", self.comps)], ["한미반도체", "한화세미텍"])
        self.assertEqual([n for _, n in P.who("SK hynix files reexamination", self.comps)], ["SK하이닉스"])

    def test_rss_date(self):
        self.assertEqual(P._day("Sat, 07 Nov 2026 03:00:00 GMT"), "2026-11-07")
        self.assertEqual(P._day("2026-11-05"), "2026-11-05")

    def test_patent_terms_skip_unrelated_license(self):
        import re
        self.assertIsNone(re.search(P.cfg()["title_re"], "홍콩, 가상자산 커스터디 라이선스 도입", re.I))
        self.assertTrue(re.search(P.cfg()["title_re"], "LG화학-SFC 청색 OLED 특허소송 쌍방 항소", re.I))


if __name__ == "__main__":
    unittest.main()
