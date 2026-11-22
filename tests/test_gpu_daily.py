"""GPU 렌털비 일일 추이 — 옛 가격표 칸 읽기·계단선·변경 구간·관문(마스터 지시 2026-11-19)"""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import gpu_daily as D  # noqa: E402

KST = timezone(timedelta(hours=9))


def page(cells):
    return "".join(f"<div>{c}</div>" for c in cells).encode()


class GpuDaily(unittest.TestCase):
    def test_coreweave_old_layout_per_gpu(self):
        raw = page(["NVIDIA HGX H100", "NVIDIA HGX H100", "8", "80", "128", "2,048", "61.44", "$49.24", "NVIDIA B200", "8", "180", "$68.80",
                    "NVIDIA HGX B300", "8", "288", "Contact sales", "NVIDIA H100 PCIe", "1", "80", "$4.25"])
        got = {r["gpu"]: r for r in D.parse_snapshot("CoreWeave", raw)}
        self.assertEqual(got["H100"]["usd_per_gpu_hr"], 6.16)
        self.assertEqual(got["H100"]["node_usd_hr"], 49.24)
        self.assertEqual(got["B200"]["usd_per_gpu_hr"], 8.6)
        self.assertIsNone(got["B300"]["usd_per_gpu_hr"])   # 문의 — 값 없음
        self.assertEqual(len(got), 3)                       # PCIe는 뺀다

    def test_nebius_old_layout_skips_commit_cards(self):
        raw = page(["NVIDIA H100 Tensor Core GPU", "$2.00", "/ hour", "NVIDIA H100 GPU", "$2.00", "/ hour",
                    "1 × H200 SXM", "141", "200", "16", "$3.50", "$2.30", "8 × H200 SXM", "1128", "$28.00",
                    "1 × H100 SXM", "80", "200", "16", "$2.95", "$2.00"])
        got = {r["gpu"]: r["usd_per_gpu_hr"] for r in D.parse_snapshot("Nebius", raw)}
        self.assertEqual(got, {"H200": 3.5, "H100": 2.95})   # 약정 카드($2.00)가 아니라 표의 온디맨드

    def test_steps_and_carry_in(self):
        obs = {("Nebius", "H100"): {"2025-12-27": 2.95, "2026-05-07": 2.95, "2026-07-12": 3.85, "2026-11-19": 4.5},
               ("CoreWeave", "B300"): {"2026-11-19": None}}
        S = D.series(obs, "2026-01-01", "2026-11-19")
        s = S[("Nebius", "H100")]
        self.assertEqual(s["points"][0], ("2026-01-01", 2.95))   # 연초 = 직전 관측값
        self.assertEqual([(x["from"], x["to"]) for x in s["steps"]], [("2026-05-07", "2026-07-12"), ("2026-07-12", "2026-11-19")])
        self.assertAlmostEqual(s["chg"], (4.5 / 2.95 - 1) * 100)
        self.assertNotIn(("CoreWeave", "B300"), S)   # 값이 하나도 없으면 선 없음
        cap = D.caption(D.summary(S, "2026-01-01", "2026-11-19"))
        self.assertIn("H100  4.50", cap)   # 간략 양식(2026-11-20)
        self.assertIn("최근 변경: Nebius 1종 +17%(7/12~11/19)", cap)
        self.assertLessEqual(len(cap.splitlines()), 8)

    def test_status_window(self):
        for h in (9, 11, 23):   # 10~11시 밖은 열지 않는다(그림도 그리지 않는다)
            self.assertEqual(D.status(datetime(2026, 11, 21, h, 30, tzinfo=KST)), {"due": False})


class MarketIndex(unittest.TestCase):
    """2026-11-21 마스터 지시 "GPU 임대료 집계가 잘 안 되는 것 같다. 추이가 제대로 안 나오기 때문이다" — 정가는 평평해서 시장 지수 참고선을 함께"""

    def test_index_summary_and_caption(self):
        obs = {("CoreWeave", "H100"): {"2025-12-16": 6.16, "2026-11-21": 6.16},
               (D.IDX, "H100"): {"2026-07-28": 2.60, "2026-11-14": 3.00, "2026-11-21": 3.09}}
        S = D.series(obs, "2026-01-01", "2026-11-21")
        summ = D.summary(S, "2026-01-01", "2026-11-21")
        self.assertAlmostEqual(summ["index"]["H100"]["1w"], 3.0, places=1)
        self.assertNotIn(D.IDX, [p for r in summ["gpus"] for p in r["prov"]])   # 제공사 줄에 섞지 않는다
        cap = D.caption(summ)
        self.assertIn("시장 지수 H100 3.09(+3.0%)", cap)
        self.assertIn("CW 연초 이후 정가 변동 없음", cap)

    def test_chart_draws_with_index_and_gap(self):
        import tempfile
        obs = {("Nebius", "H100"): {"2025-12-27": 2.95, "2026-05-07": 2.95, "2026-07-12": 3.85},
               (D.IDX, "H100"): {"2026-07-28": 2.6, "2026-11-21": 3.08}}
        from unittest import mock
        with tempfile.TemporaryDirectory() as d, mock.patch.object(D, "observations", return_value=obs):
            png, summ = D.chart("2026-01-01", "2026-11-21", path=Path(d) / "g.png")
            self.assertTrue(png.exists())
        self.assertIn("H100", summ["index"])
        self.assertEqual(summ["daily_since"], "2026-07-28")   # 일일 계열이 처음 관측된 날부터 그린다(2026-11-23)

    def test_daily_window_axis_and_caption_order(self):
        obs = {("Nebius", "H100"): {"2025-12-27": 2.95}, (D.IDX, "H100"): {"2026-09-11": 2.9, "2026-11-21": 3.1},
               (D.ORN, "H100"): {"2026-08-22": 2.7, "2026-11-21": 2.9}, (D.FLP, "H100"): {}}
        self.assertEqual(D.daily_window(obs, "2026-01-01", "2026-11-21"), "2026-08-22")
        self.assertEqual(D.daily_window(obs, "2026-10-01", "2026-11-21"), "2026-10-01")       # 요청한 시작일보다 앞서지 않는다
        self.assertIsNone(D.daily_window({("Nebius", "H100"): {"2025-12-27": 2.95}}, "2026-01-01", "2026-11-21"))
        bottom, top, step = D._daily_axis([2.46, 3.63])
        self.assertLessEqual(bottom, 2.46)
        self.assertGreaterEqual(top, 3.63)
        self.assertGreater(bottom, 0)                                                         # 0부터가 아니다 — 일일 움직임이 보이게
        self.assertAlmostEqual((top - bottom) / step, round((top - bottom) / step))
        S = D.series(obs, "2026-01-01", "2026-11-21")
        cap = D.caption(D.summary(S, "2026-01-01", "2026-11-21")).splitlines()
        self.assertIn("일일 추이", cap[0])
        self.assertTrue(cap[1].startswith("실거래 지수(Ornn)"))                               # 매일 움직이는 값이 정가보다 먼저
        self.assertLess(next(i for i, x in enumerate(cap) if x.startswith("시장 지수")), next(i for i, x in enumerate(cap) if x.startswith("정가(")))

    def test_chart_falls_back_to_list_prices_without_daily_series(self):
        import tempfile
        from unittest import mock
        obs = {("Nebius", "H100"): {"2025-12-27": 2.95, "2026-07-12": 3.85}}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(D, "observations", return_value=obs):
            png, summ = D.chart("2026-01-01", "2026-11-21", path=Path(d) / "g.png")
            self.assertTrue(png.exists())
        self.assertNotIn("daily_since", summ)

    def test_index_outliers_dropped(self):
        o = {"2026-07-28": 7.17, "2026-08-12": 68.0, "2026-09-11": 2.64, "2026-10-02": 2.77, "2026-10-10": 2.85, "2026-11-20": 3.08}
        self.assertEqual(sorted(D.index_clean(o)), ["2026-09-11", "2026-10-02", "2026-10-10", "2026-11-20"])

    def test_silicon_data_reads_given_text(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
        import gpu_rental
        u = gpu_rental.SD_PAGES[0]
        t = ('<div><span>H200</span><span>Bloomberg ticker:</span><span>--</span><a>View</a></div>'
             '<div class="text-[30px] font">$3.74</div>')
        got = gpu_rental.silicon_data({u: t})
        self.assertEqual([(r["gpu"], r["usd_per_gpu_hr"]) for r in got], [("H200", 3.74)])


if __name__ == "__main__":
    unittest.main()
