"""같은 종목 옛 리포트 정리 시험 (마스터 지시 2026-11-04)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tenbagger"))
import prune_reports as pr  # noqa: E402

R = "outputs/tenbagger/reports/"


class T(unittest.TestCase):
    def test_same_ticker_older_only(self):
        paths = [R + "20261104_EROCK.html", R + "20261104_EROCK_notion.md", R + "charts/20261104_EROCK_3.svg", R + "delivery/20261104_EROCK.json",
                 R + "20261204_EROCK.html", R + "20261104_EROCKX.html", R + "20261104_PWR.json", R + "delivery.csv", "knowledge/x/20261104_EROCK.json"]
        self.assertEqual(pr.older(paths, "20261204_EROCK"),
                         sorted([R + "20261104_EROCK.html", R + "20261104_EROCK_notion.md", R + "charts/20261104_EROCK_3.svg", R + "delivery/20261104_EROCK.json"]))

    def test_same_day_kept(self):
        self.assertEqual(pr.older([R + "20261204_EROCK.json"], "20261204_EROCK"), [])


if __name__ == "__main__":
    unittest.main()
