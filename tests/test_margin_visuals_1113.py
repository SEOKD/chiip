"""Analysis 비용·마진 시각물 정리(마스터 지시 2026-11-13) — 보이는 것만 바뀌고 계산은 그대로"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import cost_bridge_view as cb  # noqa: E402
import margin_view as mv  # noqa: E402

DP = json.loads((ROOT / "tests" / "fixtures" / "margin_lth_1113.json").read_text(encoding="utf-8"))   # LTH datapack 발췌(저장소 독립)


def titles(blocks):
    return [(b.get("chart") or {}).get("title") or b.get("title") for b in blocks]


class TestVisuals(unittest.TestCase):
    def test_cost_trend_follows_waterfall_and_contrib_chart_gone(self):
        t = titles(cb.blocks(DP))
        i = next(k for k, x in enumerate(t) if x and x.startswith("매출 → 매출총이익"))
        self.assertTrue(t[i + 1].startswith("분기 비용 비중 추이"))
        self.assertFalse(any(x and x.startswith("1년 전 대비 마진 기여") for x in t))

    def test_margin_charts_show_change_only(self):
        bl = mv.section(DP)["blocks"]
        ch = next(b["chart"] for b in bl if (b.get("chart") or {}).get("title", "").startswith("비용 요인별"))
        self.assertEqual(ch["title"], "비용 요인별 매출 대비 비중 1년 변화")
        self.assertTrue(all(len(r["bars"]) == 1 and r["bars"][0]["name"] == "변화(%p)" for r in ch["rows"]))
        bom = [b["chart"] for b in bl if (b.get("chart") or {}).get("title", "").endswith("BOM 원가 몫")]
        self.assertTrue(bom)
        self.assertTrue(all(len(r["bars"]) == 1 for c in bom for r in c["rows"]))


if __name__ == "__main__":
    unittest.main()
