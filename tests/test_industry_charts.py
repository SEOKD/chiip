"""Industry Report 시각물(마스터 지시 2026-11-22 "시각물이 부족하다. 시각물을 많이 만들어 가독성을 높여라")"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "industry"))
import auto_charts as AC  # noqa: E402

DP = {"logic": {"scenarios": [{"case": "약세", "p": 0.3, "value": 370, "kpi": "매출($B)"}, {"case": "기본", "p": 0.5, "value": 450}, {"case": "강세", "p": 0.2, "value": 530}],
                "estimates": [{"company": "A", "metric": "EPS", "chiip": 172, "street": 180}],
                "revisions": [{"metric": "30일", "up": 25, "down": 5}],
                "valuation_history": [{"name": "A", "multiple": "P/E", "now": 6.76, "low": 5.46, "high": 66.06}],
                "drivers": [{"name": "A 3분기", "volume": {"chg": 0.1}, "price": {"chg": 0.27}}],
                "market_size": {"now": {"year": 2026, "value": 250}, "forecast": [{"year": 2027, "low": 370, "high": 530}]}},
      "checkpoints": [{"date": "2026-12-01", "what": "수출", "p": 0.85}],
      "charts": [{"kind": "bars", "title": "현물", "categories": ["x"], "series": [{"name": "s", "values": [1]}], "gallery": True},
                 {"kind": "bars", "title": "수요", "categories": ["x"], "series": [{"name": "s", "values": [1]}], "after": "② 수요"}]}


class TestAutoCharts(unittest.TestCase):
    def test_numbers_come_from_datapack(self):
        ch = dict((c["title"].split(" — ")[0], c) for _, c in AC.auto(DP, [{"name": "서버", "market": -9.1, "expected": -3.0}]))
        self.assertEqual(ch["시나리오"]["kind"], "scenario")
        self.assertIn("확률 가중 442", ch["시나리오"]["title"])
        self.assertEqual(ch["시나리오"]["current"], 250)
        self.assertEqual(ch["제 추정 − 컨센서스(%)"]["rows"][0]["bars"][0]["value"], -4.4)
        self.assertEqual(ch["멀티플 밴드 위치(%, 0=5년 저점·100=고점)"]["rows"][0]["bars"][0]["value"], 2.1)
        self.assertEqual(ch["확인할 사건"]["rows"][0]["bars"][0]["value"], 85.0)
        self.assertEqual(ch["동인 분해"]["series"][1]["values"], [27.0])

    def test_place_after_table_section_or_gallery(self):
        sec = [{"h2": "② 수요", "blocks": [{"type": "p", "text": "t"}]},
               {"h2": "⑥", "blocks": [{"type": "table", "title": "시나리오 — 확률 합 1"}, {"type": "p", "text": "x"}]}]
        gal = AC.place(sec, AC.auto(DP))
        self.assertIn("현물", [c["title"] for c in gal])   # gallery 표시 + 짝 표가 없는 자동 그래프
        self.assertNotIn("수요", [c["title"] for c in gal])
        self.assertEqual(sec[1]["blocks"][1]["chart"]["kind"], "scenario")   # 표 바로 뒤
        self.assertEqual(sec[0]["blocks"][-1]["chart"]["title"], "수요")    # 절 제목으로
        self.assertGreaterEqual(AC.count({"gallery": gal, "sections": sec}), 3)

    def test_empty_datapack_makes_nothing(self):
        self.assertEqual(AC.auto({}), [])


if __name__ == "__main__":
    unittest.main()
