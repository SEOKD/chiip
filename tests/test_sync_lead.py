"""거시 지표 선행·세그먼트 전망 시험 (마스터 지시 2026-11-04)"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import sync_view as sv  # noqa: E402


def make(lead_q=2):
    """지표가 lead_q분기 앞서는 세그먼트 매출(전년 대비 증가율이 지표의 lead_q분기 전 증가율 × 0.8)"""
    months, val = {}, 100.0
    g = [0.3 * math.sin(i / 3.0) for i in range(80)]   # 월별 전년 대비 증가율 패턴
    for i in range(80):
        y, m = 2019 + i // 12, i % 12 + 1
        months[f"{y}-{m:02d}"] = 100 * (1 + g[i])
    ind = {"source": "ppi", "input": "x", "country": "us", "label": "지표", "segment": "A"}
    hist = {"inputs": {"x": {"ppi": {"us": months}}}}
    ends = {}
    q, seg, tot = [], [], []
    for i in range(6, 24):   # 2020Q3 ~ 2024Q4
        y, qq = 2019 + i // 4, i % 4 + 1
        end_m = qq * 3
        lab = f"{y}Q{qq}"
        ends[lab] = (y, end_m)
    iq = sv.quarterize({k: v for k, v in months.items()}, {**ends, **{sv.shift_q(l, -j): ((ends[l][0] * 12 + ends[l][1] - 1 - 3 * j) // 12, (ends[l][1] - 1 - 3 * j) % 12 + 1) for l in ends for j in range(1, 9)}}, True)
    ig = sv.growth(iq, 4)
    base = {}
    for lab in sorted(ends):
        prev = sv.shift_q(lab, -4)
        x = ig.get(sv.shift_q(lab, -lead_q))
        base[lab] = (base.get(prev) or 100.0) * (1 + 0.8 * x) if x is not None and prev in base else 100.0
        y, m = ends[lab]
        q.append({"period": f"{y}-{m:02d}-28", "rev": base[lab] * 3, "op": base[lab] * 0.3})
        seg.append({"period": f"{y}-{m:02d}-28", "rev": base[lab]})
    dp = {"sync": {"indicators": [ind]}, "quarters_hist": {"q": q}, "segments_hist": {"segments": {"A": seg}}}
    return dp, hist


class T(unittest.TestCase):
    def test_lead_found_on_segment_and_path(self):
        dp, hist = make(2)
        c = sv.compute(dp, history=hist)
        r = c["rows"][0]
        self.assertEqual(r["target"], "A")
        self.assertEqual(r["rev"]["lag"], 2)
        self.assertTrue(r["rev"]["sig"])
        self.assertEqual([p["q"] for p in r["path"]], [sv.shift_q(c["last"], 1), sv.shift_q(c["last"], 2)])

    def test_lags_cover_four_quarters(self):
        self.assertEqual(max(sv.LAGS), 4)


if __name__ == "__main__":
    unittest.main()
