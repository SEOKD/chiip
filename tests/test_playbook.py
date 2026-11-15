"""투자 포인트·모멘텀 타임라인·언제 사서 언제 팔아야 할까(마스터 지시 2026-11-16) — scripts/tenbagger/playbook_view.py"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import playbook_view as pv  # noqa: E402

DP = {"playbook": {
    "points": [{"title": f"포인트{i}", "claim": "명제", "evidence": "1Q 매출 $479M(+115%)", "variant": "컨센서스는 2H 인플렉션을 반만 반영", "proof": "3Q 가이던스 $650M+", "source": "1Q 콜"} for i in range(3)],
    "momentum": [{"date": "2026-04-13", "status": "완료", "kind": "생성", "event": "인수 발표", "reaction": "+12%"},
                 {"date": "2026-11-05", "status": "완료", "kind": "매크로", "event": "섹터 급락", "reaction": "-18%"},
                 {"date": "2026-12 초(예상)", "status": "예정", "kind": "확인", "event": "2Q 실적", "check": "3Q 가이던스 $650M+", "then": "충족 → 기본, 미달 → 약세"},
                 {"date": "2027-02", "status": "예정", "kind": "확인", "event": "1.6T 첫 매출", "check": "광 매출 분기 $150M+"}],
    "trade": {"watch": "11/5 저점 부근", "confirm": "3Q 가이던스 $650M+", "invalid": "3Q 가이던스 $600M 미만", "trim": "기본~강세 밸류", "style": "실적일 ±15~20%가 기본 변동"}}}
V = {"price": 131.5, "bear": 95.0, "base": 165.0, "bull": 291.0, "target": 172.0}
SUP = [{"mid": 118.0, "lo": 112.0, "hi": 124.0}, {"mid": 140.0, "lo": 138.0, "hi": 142.0}]
F = lambda x: f"${x:,.0f}"


class TestPlaybook(unittest.TestCase):
    def test_complete_passes_check(self):
        self.assertEqual(pv.check(DP), [])
        self.assertTrue(pv.check({}))

    def test_zones_from_engine_values(self):
        z = {x["k"]: x for x in pv.zones(V, SUP, F)}
        self.assertEqual(z["관찰 구간"]["price"], "$112~$124")             # 지금 아래 가장 가까운 지지
        self.assertAlmostEqual(z["관찰 구간"]["up"], 172 / 118 - 1)
        self.assertIn("$172", z["차익 고민 1차"]["price"])
        self.assertIn("$291", z["차익 고민 2차"]["price"])

    def test_summary_items_and_no_trade_orders(self):
        t = pv.summary_trade(DP, V, SUP, F)
        self.assertEqual(t["q"], "언제 사서 언제 팔아야 할까?")
        self.assertIn("매매·비중 지시가 아니다", t["a"])
        self.assertNotIn("비중을", t["a"])
        self.assertIn("2Q 실적", pv.summary_momentum(DP)["a"])
        self.assertEqual(pv.summary_points(DP)["a"].count("\n"), 2)        # 한 줄에 하나

    def test_blocks(self):
        b = pv.blocks(DP, V, SUP, F)
        self.assertEqual([x["text"] for x in b if x["type"] == "h3"], ["투자 포인트", "모멘텀 생성·소멸 타임라인", "언제 사서 언제 팔아야 할까?"])


if __name__ == "__main__":
    unittest.main()
