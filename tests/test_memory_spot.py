"""Memory Spot — 채널 변화율 줄 파싱·최소제곱 추정·달러 기준점(마스터 지시 2026-11-19)"""
import math
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import memory_spot as M  # noqa: E402

POST = {"id": 1, "channel": "merITz_tech", "at": "2026-11-17T07:59:00+09:00", "url": "https://t.me/merITz_tech/1",
        "text": "★ 메모리 스팟가격\n DRAM(DDR4 8Gb: 1D -0.07%, 1W +0.26%, 1M -0.02%)\n         (DDR5 16Gb: 1D +0.11%, 1W +0.28%, 1M -0.44%)\n NAND(MLC 64Gb: 1D +0.42%, 1W +0.42%, 1M +4.96%)"}


def synth(days=70, gap=()):
    """매 거래일 +1%인 가격 — 게시일 = 다음 평일. gap 날짜엔 글이 없다"""
    rows, p, d = [], 100.0, date(2026, 1, 5)
    price = {}
    while len(price) < days:
        if d.weekday() < 5:
            price[d] = p
            p *= 1.01
        d += timedelta(days=1)
    ds = sorted(price)
    for i, t in enumerate(ds[1:], 1):
        if t in gap:
            continue
        def ago(n):
            ref = M._month_back(t) if n == 30 else t - timedelta(days=n)
            old = [x for x in ds if x <= ref]
            return (price[t] / price[old[-1]] - 1) * 100 if old else 0.0
        rows.append({"post_id": i, "channel": "c", "posted_at": datetime(t.year, t.month, t.day, 8).isoformat(), "product": "DDR5 16Gb",
                     "d1": round((price[t] / price[ds[i - 1]] - 1) * 100, 2), "w1": round(ago(7), 2), "m1": round(ago(30), 2), "url": ""})
    return rows


class MemorySpot(unittest.TestCase):
    def test_parse(self):
        r = M.parse_post(POST)
        self.assertEqual([x["product"] for x in r], ["DDR4 8Gb", "DDR5 16Gb", "MLC 64Gb"])
        self.assertEqual((r[1]["d1"], r[1]["w1"], r[1]["m1"]), (0.11, 0.28, -0.44))

    def test_gap_filled_by_week(self):
        gap = {date(2026, 2, 17), date(2026, 2, 18)}   # 휴일로 글 이틀 빠짐 — 1D만 이으면 2% 모자란다
        s = M.series(synth(gap=gap), "DDR5 16Gb", "2026-01-01")
        n = len(s["points"]) - 1 + 2   # 빠진 이틀도 실제로는 올랐다
        true = (1.01 ** n - 1) * 100
        self.assertAlmostEqual(s["chg"]["YTD"], true, delta=0.6)
        self.assertEqual(s["unit"], "지수")

    def test_anchor_usd(self):
        rows = synth()
        a = [{"product": "DDR5 16Gb", "date": "2026-02-02", "usd": 40.0}]
        s = M.series(rows, "DDR5 16Gb", "2026-01-01", a)
        self.assertEqual(s["unit"], "USD")
        node = date.fromisoformat(s["anchors_used"][0]["node"])
        self.assertGreater(node, date(2026, 2, 2))
        self.assertAlmostEqual(dict(s["points"])[node], 40.0, delta=0.01)
        self.assertTrue(math.isclose(s["misfit_pct"], 0, abs_tol=1e-9))


class Blend(unittest.TestCase):   # TrendForce 기본 + 메리츠 보강(2026-11-20)
    def test_bridge_meets_next_obs_and_tail(self):
        tf = [(date(2026, 1, 5), 100.0), (date(2026, 1, 9), 110.0)]
        mz = [(date(2026, 1, 6), 50.0), (date(2026, 1, 7), 52.0), (date(2026, 1, 8), 53.0), (date(2026, 1, 9), 54.0), (date(2026, 1, 10), 55.0), (date(2026, 1, 13), 56.1)]
        out = M.blend(tf, mz)   # 메리츠 글 날짜 → 세션 = 직전 평일
        tail = [p for p in out if p[0] > date(2026, 1, 9)]
        self.assertTrue(all(src == "mz" for _, _, src in tail))
        self.assertAlmostEqual(tail[-1][1], 110.0 * 56.1 / 55.0)   # 마지막 관측 뒤는 메리츠 변화율 그대로
        mid = [v for d, v, src in out if src == "mz" and d < date(2026, 1, 9)]
        self.assertTrue(all(100.0 < v < 110.0 for v in mid))      # 사이 구간은 다음 관측에 맞게 보정
        self.assertEqual([p for p in M.blend(tf, mz, interior=False) if p[0] < date(2026, 1, 9) and p[2] == "mz"], [])


class TestNandDaily(unittest.TestCase):
    """NAND도 일별로(2026-11-23 마스터 지시) — 1D를 그대로 쌓은 경로가 관측 사이를 채운다"""
    ROWS = [{"product": "MLC 64Gb", "posted_at": f"2026-01-{d:02d}T09:00:00+09:00", "d1": v} for d, v in
            ((6, "0.0"), (7, "0.0"), (8, "2.0"), (9, "0.0"), (12, "0.0"), (13, "1.0"), (14, ""))]

    def test_raw_path_moves_only_on_change_days(self):
        path = M.raw_path(self.ROWS + [{"product": "DDR5 16Gb", "posted_at": "2026-01-08T09:00:00+09:00", "d1": "9.9"}], "MLC 64Gb")
        vals = [round(v, 4) for _, v in path]
        self.assertEqual(vals, [1.0, 1.0, 1.02, 1.02, 1.02, 1.0302, 1.0302])      # 다른 제품은 섞지 않고, 빈 1D는 변화 없음으로
        self.assertEqual(path[2][0], date(2026, 1, 8))

    def test_blend_keeps_step_day_between_weekly_observations(self):
        tf = [(date(2026, 1, 5), 10.0), (date(2026, 1, 12), 10.3)]                 # 주 1회 관측 — 한 주에 +3%
        pts = M.blend(tf, M.raw_path(self.ROWS, "MLC 64Gb"), True)
        mid = {d: v for d, v, src in pts if src == "mz" and d < date(2026, 1, 12)}
        self.assertEqual(sorted(mid), [date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9)])   # 세션 = 글 날짜의 직전 평일
        self.assertGreater(mid[date(2026, 1, 7)] / mid[date(2026, 1, 6)] - 1, 0.015)   # 1/8 글의 +2%는 1/7 세션에서 계단으로 보인다
        self.assertLess(abs(mid[date(2026, 1, 8)] / mid[date(2026, 1, 7)] - 1), 0.005)  # 그 밖의 날은 거의 그대로(관측값과 만나는 보정만)
        self.assertEqual(pts[-1][2], "mz")                                          # 마지막 관측 뒤도 일별로 잇는다


if __name__ == "__main__":
    unittest.main()
