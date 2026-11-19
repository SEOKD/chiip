"""PeeringDB 대체 데이터 수집기 시험 (2026-11-20, ADR-049)"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import peeringdb as pdb  # noqa: E402

C = pdb.cfg()


class T(unittest.TestCase):
    def test_request_budget_fits(self):
        # fac 1 + netfac 1 + netixlan 1 + IX별 1 — 회차 상한 안
        self.assertLessEqual(3 + len(C["ixs"]), C["max_requests"])
        self.assertGreaterEqual(C["gap_sec"], 1)

    def test_budget_stops(self):
        b = pdb.Budget({"max_requests": 0, "gap_sec": 0})
        with self.assertRaises(RuntimeError):
            b.get("fac")

    def test_diff_new_facility_and_jump(self):
        nid = next(k for k, v in C["networks"].items() if v["kind"] == "AI 클라우드")
        fid = next(iter(C["facilities"]))
        prev_pres = {str(nid): {"fac": {"1": "2024-01-01"}, "ix": {}}}
        pres = {str(nid): {"fac": {"1": "2024-01-01", "999": "2026-11-20"}, "ix": {}}}
        fac = {str(fid): {"net_count": 120, "ix_count": 1}}
        prev = {str(fid): {"net_count": "100"}}
        ch = pdb.diff(C, fac, prev, pres, prev_pres, "2026-11-20")
        types = {x["type"] for x in ch}
        self.assertIn("new_fac", types)
        self.assertIn("fac_net_jump", types)

    def test_first_run_is_baseline(self):
        nid = next(iter(C["networks"]))
        ch = pdb.diff(C, {}, {}, {str(nid): {"fac": {"5": "x"}, "ix": {}}}, {}, "2026-11-20")
        self.assertEqual(ch, [])

    def test_no_contact_fields_requested(self):
        src = Path(pdb.__file__).read_text(encoding="utf-8")
        for bad in ("poc", "email", "phone"):
            self.assertNotIn(f'"{bad}', src)


if __name__ == "__main__":
    unittest.main()
