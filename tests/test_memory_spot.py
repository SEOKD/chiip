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


if __name__ == "__main__":
    unittest.main()
