"""해외 데스크(2026-11-21 마스터 지시 — 해외 상장사 자료·통계에서 한국 전자부품·반도체 기사 소재, 국내 미보도 관문)"""
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "article"))
import overseas_desk as D  # noqa: E402
import pitch_feedback as pf  # noqa: E402

MD = """## 기사① 아마다
- 야마 유형: 공급사 장부에 찍힌 한국
- 국내 보도 검색:
  - 검색어 "아마다 유리기판" · 웹 검색 · 2026-11-21 · 0건
  - 검색어 "아마다 삼성전기" · 웹 검색 · 2026-11-21 · 0건
- 판정: 국내 미보도
"""


class TestDesk(unittest.TestCase):
    def test_config_and_counterparties(self):
        c = D.cfg()
        self.assertEqual(set(c["archetypes"]), {"customer", "competitor", "supplier", "data", "tech", "silence"})
        names = {n for x in D.counterparties() for n in x["names"]}
        for n in ("SMIC", "UMC", "Yageo", "X-FAB", "IQE", "CXMT"):   # 중국·대만·EU·영국
            self.assertIn(n, names)
        korea = {k for x in D.counterparties() for k in x["korea"]}
        self.assertTrue(set(D.TARGETS) <= korea)

    def test_kind_and_match(self):
        c = D.cfg()
        self.assertEqual(D.kind_of("HBM 고객", c), "customer")
        self.assertEqual(D.kind_of("8인치 파운드리 경쟁", c), "competitor")
        self.assertEqual(D.kind_of("증착 장비", c), "supplier")
        cp = D.match_cp("STMicroelectronics invests more than 100 million euros", [], D.counterparties())
        self.assertEqual(cp["hit"], "STMicroelectronics")
        self.assertIsNone(D.match_cp("Intelligent systems", [], D.counterparties()))   # 'Intel'이 단어 일부로 걸리지 않는다

    def test_gap_score(self):
        self.assertEqual(D.gap_score(["무라타"], ["삼성전기 MLCC"])[0], 2.0)
        self.assertEqual(D.gap_score(["무라타"], ["무라타 증설"] * 3)[0], 0.0)

    def test_data_only_when_new(self):
        st = Path(tempfile.mkdtemp()) / "s.json"
        now = datetime(2026, 11, 21, 6, tzinfo=D.KST)
        x = [{"title": "메모리 — 미국 수입액 +617%(2026-09)"}]
        self.assertEqual(len(D.fresh_data(x, now, st)), 1)
        self.assertEqual(len(D.fresh_data(x, now + timedelta(days=2), st)), 1)
        self.assertEqual(len(D.fresh_data(x, now + timedelta(days=3), st)), 0)          # 같은 숫자는 사흘째부터 빠진다
        self.assertEqual(len(D.fresh_data([{"title": "메모리 — 미국 수입액 +500%(2026-10)"}], now + timedelta(days=3), st)), 1)

    def test_novelty_gate(self):
        self.assertEqual(D.novelty_gate(MD), [])
        bad = D.novelty_gate(MD.replace('  - 검색어 "아마다 삼성전기" · 웹 검색 · 2026-11-21 · 0건\n', "").replace("국내 미보도", "보류"))
        self.assertTrue(any("검색어" in b for b in bad))
        self.assertTrue(any("판정" in b for b in bad))

    def test_buttons_offset(self):
        b = pf.buttons("20261121", 2, start=2)
        self.assertEqual(b[0][0], ("② 채택", "pitch:20261121:2:y"))
        self.assertEqual(b[0][1][1], "pitch:20261121:3:y")


if __name__ == "__main__":
    unittest.main()
