"""펄스 실적 즉시 보고·동시 실적 5건 (마스터 지시 2026-11-03)"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
import pulse  # noqa: E402


def hit(adsh, name, items):
    return adsh, {"display_names": [name], "items": items, "file_date": "2026-11-03"}


class TestEarnings(unittest.TestCase):
    def test_reports_only_universe_2_02_after_seed(self):
        hits = [hit("1", "Lattice Semiconductor Corp  (LSCC)  (CIK 0000855658)", ["2.02", "9.01"]),
                hit("2", "Other Co  (ZZZZ)  (CIK 0000000001)", ["2.02"]),
                hit("3", "Lattice Semiconductor Corp  (LSCC)  (CIK 0000855658)", ["5.02"])]
        with mock.patch.object(pulse, "earnings_universe", return_value={"LSCC": "us-lscc"}), mock.patch.object(pulse.sea, "fetch_hits", return_value=hits):
            st = {"earn_seen": []}
            out = pulse.fetch_earnings(st)
            self.assertEqual([x["ticker"] for x in out], ["LSCC"])
            self.assertEqual(pulse.fetch_earnings(st), [])
            self.assertEqual(pulse.fetch_earnings({}), [])   # 첫 회차는 기존 건을 씨앗으로만

    def test_select_tops_up_earnings_to_five(self):
        src = [{"source_class": "공시", "title": f"Co{i} third quarter results"} for i in range(20)]
        picked = pulse.select(src)
        self.assertEqual(sum(map(pulse.is_earnings, picked)), max(pulse.TOP["공시"], pulse.EARNINGS_MAX))


if __name__ == "__main__":
    unittest.main()
