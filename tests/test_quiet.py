"""조용한 매집형 상승 발굴 시험 (마스터 지시 2026-10-29 "FormFactor·Nova 같은 엣지 중소형 반드시 관측 — 수급·관심은 제한적이지만
기관 자금이 들어오며 조용하면서 꾸준히 상승하는 종목을 잘 발굴")"""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
sys.path.insert(0, str(ROOT / "radar"))

import quiet  # noqa: E402
from pollers import common  # noqa: E402

C = {**quiet.DEFAULT, "weights": dict(quiet.DEFAULT["weights"]), "gates": dict(quiet.DEFAULT["gates"])}


def path_steady(n=300, up=0.002):
    """매일 조금씩 오르는 경로(가끔 작은 하락)"""
    out, p = [], 100.0
    for i in range(n):
        p *= (1 + up) if i % 5 else (1 - up / 2)
        out.append(p)
    return out


def path_jumpy(n=300):
    """같은 기간 수익률을 몇 번의 급등으로 — 나머지 날은 조금씩 하락"""
    out, p = [], 100.0
    for i in range(n):
        p *= 1.25 if i % 60 == 30 else 0.9995
        out.append(p)
    return out


class TestTrend(unittest.TestCase):
    def test_information_discreteness(self):
        id_s, r_s = quiet.info_discreteness(path_steady())
        id_j, r_j = quiet.info_discreteness(path_jumpy())
        self.assertGreater(r_s, 0)
        self.assertGreater(r_j, 0)
        self.assertLess(id_s, id_j)        # 꾸준한 상승(Frog in the Pan)의 ID가 더 낮다
        self.assertLess(id_s, -0.5)

    def test_r2_and_drawdown(self):
        self.assertGreater(quiet.trend_r2(path_steady()), 0.95)
        down = [100 * (1 - 0.003 * i) for i in range(130)]
        self.assertLess(quiet.trend_r2(down), -0.9)
        self.assertAlmostEqual(quiet.max_drawdown([100, 120, 90, 110]), 0.25)

    def test_profile_trend_and_gate(self):
        f = {"price": 99.23, "ma50": 117.2, "ma200": 113.9, "high_52w": 160.27, "low_52w": 47.33}   # FormFactor 2026-10-29
        t = quiet.trend_features(f, [])
        self.assertEqual(t["basis"], "개요")
        self.assertLess(t["p_ma200"], 0)
        self.assertEqual(quiet.gate(t, C), ["200일선 아래", "52주 고점의 62%"])
        self.assertEqual(quiet.gate(quiet.trend_features({}, []), C), ["추세 자료 없음"])   # 모르면 상승으로 치지 않는다
        ok = quiet.trend_features({"price": 150, "ma50": 140, "ma200": 120, "high_52w": 155}, [])
        self.assertEqual(quiet.gate(ok, C), [])
        self.assertGreater(quiet.trend_value(ok), 0.5)


class TestAccumulation(unittest.TestCase):
    def test_ats_shift_and_retail(self):
        wk = {}
        for i in range(12):
            ats = 100.0 if i < 8 else 160.0             # 최근 4주 ATS(기관 블록) 비중 상승
            wk[f"2026-08-{i + 1:02d}"] = {"ats": ats, "otc": 100.0, "retail": 10.0}
        a = quiet.accumulation_features(wk)
        self.assertAlmostEqual(a["ats_shift"], 160 / 260 - 0.5, places=6)
        self.assertAlmostEqual(a["retail_share"], 10 / 260, places=6)
        self.assertGreater(quiet.accumulation_value(a), 0.5)
        self.assertEqual(quiet.accumulation_features({})["ats_shift"], None)


class TestScoring(unittest.TestCase):
    def test_band_fallback_and_order(self):
        rows = [{"id": f"x{i}", "band": "B1" if i < 3 else "B2", "raw": {"trend": i / 10, "accumulation": None, "neglect": None,
                                                                          "fundamental": 0.1 * i, "edge": None}} for i in range(8)]
        quiet.score_rows(rows, C)
        b1 = [r for r in rows if r["band"] == "B1"]
        self.assertEqual(len(b1), 3)                    # 구간 안 비교 대상 < 5 → 전체 백분위
        self.assertIn("accumulation", rows[0]["missing"])
        self.assertGreater(rows[7]["score"], rows[0]["score"])


class TestObservation(unittest.TestCase):
    def test_generic_names_need_aliases(self):
        self.assertFalse(common._distinct("Nova"))
        self.assertFalse(common._distinct("Box"))
        self.assertTrue(common._distinct("FormFactor"))
        ents = {cid: names for cid, names, _ in common.discovery_entities()}
        self.assertIn("Nova Ltd", ents["us-nvmi"])
        self.assertNotIn("Nova", ents["us-nvmi"])

    def test_matching_and_sec_watch(self):
        common._ALIAS_CACHE = None
        self.assertIn("us-nvmi", common.match_entities("Nova Ltd. reports record revenue"))
        self.assertNotIn("us-nvmi", common.match_entities("Bossa Nova jazz festival returns"))
        self.assertIn("co-formfactor", common.match_entities("FormFactor raises guidance on HBM probe cards"))
        w = common.edge_watch_entries()
        ids = [e["id"] for e in w]
        self.assertEqual(len(ids), len(set(ids)))       # 발굴 후보·시드 중복 없이
        for cid in ("co-formfactor", "us-nvmi", "us-onto", "us-camt"):
            self.assertIn(cid, ids)
        self.assertTrue(all(e["code"].endswith(".US") for e in w))


if __name__ == "__main__":
    unittest.main()
