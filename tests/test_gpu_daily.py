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


if __name__ == "__main__":
    unittest.main()
