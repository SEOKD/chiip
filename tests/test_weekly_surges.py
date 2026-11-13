"""Weekly '급등 종목, 왜 올랐나' 관문(마스터 지시 2026-11-14)"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "weekly"))
import surges  # noqa: E402

MOVERS = [{"key": k, "rows": [{"ticker": t, "name_ko": n, "desc_ko": "사업", "pct_change": p}]}
          for k, t, n, p in (("US", "AAA", "에이", "21.2"), ("EU", "BBB", "비", "25.4"), ("JP", "1111", "씨", "48.1"), ("KR", "000001", "디", "66.6"))]


def item(region, ticker, kind="실적"):
    return {"region": region, "ticker": ticker, "kind": kind, "why": "실적 발표에서 가이던스 상향", "source": "회사 실적 발표", "next": "다음 분기 실적",
            "routes": ["회사 공시", "TradingView 뉴스"]}


class TestSurges(unittest.TestCase):
    def full(self):
        return [item("US", "AAA"), item("EU", "BBB"), item("JP", "1111", "주주환원"), item("KR", "000001", "업종 동조")]

    def test_build_takes_pct_from_table_and_orders_markets(self):
        rows = surges.build({"surges": list(reversed(self.full()))}, MOVERS)
        self.assertEqual([r["market"] for r in rows], ["미국", "유럽", "일본", "한국"])
        self.assertEqual(rows[3]["pct"], 66.6)
        self.assertIn("디 +67% — 업종 동조", "\n".join(surges.md_lines(rows)))
        self.assertIn("회사 외 요인", surges.html_section(rows))

    def test_rejects_stock_not_in_table(self):
        with self.assertRaises(ValueError):
            surges.build({"surges": self.full()[:3] + [item("KR", "999999")]}, MOVERS)

    def test_rejects_missing_market(self):
        with self.assertRaises(ValueError):
            surges.build({"surges": self.full()[:3] + [item("US", "AAA")]}, MOVERS)

    def test_rejects_unknown_kind_and_missing_source(self):
        bad = self.full()
        bad[0]["kind"] = "급등"
        with self.assertRaises(ValueError):
            surges.build({"surges": bad}, MOVERS)
        bad = self.full()
        bad[1]["source"] = ""
        with self.assertRaises(ValueError):
            surges.build({"surges": bad}, MOVERS)


    def test_routes_needed(self):   # 경로 하나만 보고 원인을 단정하지 않는다(2026-11-14)
        bad = self.full()
        bad[0]["routes"] = ["회사 공시"]
        with self.assertRaises(ValueError):
            surges.build({"surges": bad}, MOVERS)

    def test_kr_dart_filing_blocks_outside_cause(self):   # 46주차 심텍홀딩스: Awake에 3분기 잠정실적이 있는데 '업종 동조'
        man = {t: {"dart": 0} for t in ("AAA", "BBB", "1111")} | {"000001": {"dart": 4}}
        with self.assertRaises(ValueError):
            surges.build({"surges": self.full()}, MOVERS, manifest=man)
        ok = self.full()
        ok[3]["kind"] = "실적"
        self.assertEqual(len(surges.build({"surges": ok}, MOVERS, manifest=man)), 4)
        with self.assertRaises(ValueError):   # 근거 묶음을 안 만든 종목
            surges.build({"surges": ok}, MOVERS, manifest={"AAA": {"dart": 0}})

    def test_banned_no_reason_phrases(self):
        sys.path.insert(0, str(ROOT / "scripts" / "weekly"))
        import render
        c = render.cfg()
        for bad in ("엔비디아 CEO 사임, 이유는 공시에 없다", "지주사 자체 사건은 찾지 못했다", "사유는 없다"):
            with self.assertRaises(ValueError):
                render.lint(bad, c)
        render.lint("업종 동조는 회사 발표 없이 같은 업종의 사건에 따라 움직인 것", c)


if __name__ == "__main__":
    unittest.main()
