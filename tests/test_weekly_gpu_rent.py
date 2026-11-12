"""Weekly Review Nebius GPU 렌털료 고정 블록(scripts/weekly/gpu_rent.py) — 2026-11-13 마스터 지시"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "weekly"))
import gpu_rent as G  # noqa: E402


def r(d, prov, gpu, term, v, cfg="x"):
    return {"date": d, "provider": prov, "gpu": gpu, "config": cfg, "term": term, "usd_per_gpu_hr": v}


class TestGpuRent(unittest.TestCase):
    def test_no_change_still_shown_and_vs_index(self):
        rows = [r("2026-11-10", "Nebius", "H100", "온디맨드", "4.5"), r("2026-11-13", "Nebius", "H100", "온디맨드", "4.5"),
                r("2026-11-13", "Silicon Data 지수", "H100", "시장 지수(인용)", "3.0")]
        L = G.md_lines({"as_of": "2026-11-14"}, rows)
        txt = "\n".join(L)
        self.assertIn("변화 없음", txt)
        self.assertIn("+50.0%", txt)                       # Nebius ÷ 지수 괴리
        self.assertIn("2일치", txt)                        # 수집한 날 수
        self.assertIn("비교 불가", txt)                     # 값 없는 GPU

    def test_week_over_week_change(self):
        rows = [r("2026-11-10", "Nebius", "H100", "온디맨드", "4.0"), r("2026-11-17", "Nebius", "H100", "온디맨드", "4.4")]
        b = G.build("2026-11-17", rows)
        h = next(x for x in b["rows"] if x["gpu"] == "H100")
        self.assertAlmostEqual(h["wk"], 10.0)
        self.assertEqual(b["changed"], ["H100"])
        self.assertEqual(len(h["trend"]), 2)               # 주간 종가 2점 → 추이 그림
        self.assertIn("<svg", G.html_section({"as_of": "2026-11-17"}, rows))

    def test_suspect_preemptible_hidden_and_old_weeks_skipped(self):
        rows = [r("2026-11-13", "Nebius", g, "선점형(from)", "0.79") for g in ("H100", "H200", "L40S", "RTX PRO 6000")]
        rows += [r("2026-11-13", "Nebius", g, "온디맨드", "2") for g in ("H100", "H200", "L40S", "RTX PRO 6000")]
        self.assertTrue(G.build("2026-11-13", rows)["pre_bad"])
        self.assertEqual(G.md_lines({"as_of": "2026-11-07"}, rows), [])   # 추적 전 주차는 절 없음


if __name__ == "__main__":
    unittest.main()
