"""ADR-042 — Analysis 양식 후속: 시세 파일·동인 동기·해자 기준선·동종 규모·가이던스 해 경고"""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for sub in ("scripts/valuation/v2", "radar/markets", "radar"):
    sys.path.insert(0, str(ROOT / sub))
import build_drivers  # noqa: E402
import multiples  # noqa: E402
import prices_free  # noqa: E402
import yaml  # noqa: E402

CFG = yaml.safe_load((ROOT / "config" / "tenbagger.yaml").read_text(encoding="utf-8"))


class TestTvPrices(unittest.TestCase):
    def test_symbols_cover_drivers(self):
        syms = prices_free.tv_symbols()
        self.assertGreater(len(syms), 50)
        self.assertTrue(all(":" in s for s in syms.values()))

    def test_put_tv_writes_entity_file(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "q.json"
            f.write_text(json.dumps({"data": {"NYSE:LTH": {"close": 46.52}, "XX:NONE": {"close": 1}}}), encoding="utf-8")
            with mock.patch.object(prices_free, "PRICES", Path(d)), \
                    mock.patch.object(prices_free, "tv_symbols", return_value={"co-lth": "NYSE:LTH"}):
                n, day = prices_free.put_tv(f, "2026-11-13")
                n2, _ = prices_free.put_tv(f, "2026-11-13")   # 같은 날은 한 줄로
                with (Path(d) / "co-lth.csv").open(encoding="utf-8") as fh:
                    rows = list(csv.DictReader(fh))
        self.assertEqual((n, n2, day), (1, 1, "2026-11-13"))
        self.assertEqual([(r["date"], float(r["close"])) for r in rows], [("2026-11-13", 46.52)])


class TestMoatBaseline(unittest.TestCase):
    def test_average_moat_nets_to_zero(self):
        cfg = CFG["multiple_select"]
        self.assertGreater(cfg.get("moat_baseline", 0), 0)
        mm = {"basis": "pe_fwd", "peers": [{"pe_fwd": 25.0}] * 3,
              "horizons": [{"h": 1, "key": "pe_fwd", "label": "Fwd 1Y P/E", "current": 25.0, "peer_range": {"p50": 25.0}, "rational": {"p50": 25.0}}], "sentiment": {"n": 5}}
        none = multiples.select_multiple(mm, {"moat": {"items": []}, "narrative": {}}, cfg)
        weak = multiples.select_multiple(mm, {"moat": {"items": [{"kind": "a에 따른 b", "verdict": "강함"}]}, "narrative": {}}, cfg)
        self.assertEqual(none["value"], 25.0)   # 해자 항목이 없으면 기준선도 빼지 않는다
        self.assertLess(weak["value"], 25.0 * (1 + 0.04))


class TestGuidanceYear(unittest.TestCase):
    def test_guidance_vs_consensus_warns(self):   # CBRS: 가이던스 0.95 vs 컨센서스 FY2026 0.885
        f = ROOT / "knowledge/models/companies/us-cbrs/datapack.json"
        if not f.exists():
            self.skipTest("us-cbrs datapack 없음")
        dp = json.loads(f.read_text(encoding="utf-8"))
        dp["guidance"] = dict(dp["guidance"], rev_fy0=[0.94, 0.96])
        dp["guidance"].pop("basis_note", None)
        with mock.patch("sys.stdout"):
            warned = build_drivers.build(dp)["provenance"]["rev0"]
            dp["guidance"]["basis_note"] = "FY2026 GAAP 매출 — 컨센서스와 같은 기준"
            ok = build_drivers.build(dp)["provenance"]["rev0"]
        self.assertIn("컨센서스 첫 해", warned)
        self.assertNotIn("⚠", ok)


class TestSyncWarns(unittest.TestCase):
    def test_manual_driver_drift(self):   # AMAT: 수기 순차입 −6.76 vs datapack −2.01
        import run
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "knowledge/models/companies/co-x"
            p.mkdir(parents=True)
            (p / "datapack.json").write_text("{}", encoding="utf-8")
            co = {"id": "co-x", "market": {"price": 100.0, "shares": 1.0, "net_debt": -6.761}}
            auto = {"market": {"shares": 1.0, "net_debt": -2.005}}
            with mock.patch.object(run, "ROOT", Path(d)), mock.patch.object(build_drivers, "build", return_value=auto):
                w = run.sync_warns(co)
                same = run.sync_warns(dict(co, market={"price": 100.0, "shares": 1.0, "net_debt": -2.0}))
                why = run.sync_warns(dict(co, market=dict(co["market"], why="분기 뒤 자사주 매입 반영")))
        self.assertTrue(any("순차입" in x for x in w))
        self.assertEqual((same, why), ([], []))


if __name__ == "__main__":
    unittest.main()
