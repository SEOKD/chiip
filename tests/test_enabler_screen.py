"""'핵심 솔루션 + 반복 매출' 발굴 채널 시험 (마스터 지시 2026-11-18, ADR-047)"""
import json
import re
import sys
import unittest
import urllib.parse
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "discovery"))
import enabler_screen as es  # noqa: E402

NPKI = "NPK International Inc.  (NPKI)  (CIK 0000071829)"
REIT = "Rental Realty Trust  (RRT)  (CIK 0000000001)"
OTHER = "Big Rental Co  (BRC)  (CIK 0000000002)"


def fake(url):
    if "EntityPublicFloat" in url:
        return json.dumps({"data": [{"cik": 71829, "val": 683700000}, {"cik": 2, "val": 900000000}, {"cik": 1, "val": 500000000}]})
    if "OperatingLeaseLeaseIncome" in url:
        return json.dumps({"data": [{"cik": 2, "val": 300}]})
    if "/frames/" in url:
        return json.dumps({"data": [{"cik": 2, "val": 1000}, {"cik": 71829, "val": 217489000}]})
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
    hits = []
    if '"rental fleet"' in q and ('"transmission" "utilities"' in q or '"data center construction"' in q):
        hits = [NPKI, REIT]
    elif '"rental revenue"' in q and '"transmission and distribution"' in q:
        hits = [NPKI, OTHER]
    elif q in ('"replace traditional"', '"site access"'):
        hits = [NPKI, OTHER]
    return json.dumps({"hits": {"hits": [{"_source": {"display_names": [n], "adsh": f"{i}-{q}", "form": "10-K", "file_date": "2026-03-01"}}
                                         for i, n in enumerate(hits)]}})


class Enabler(unittest.TestCase):
    def test_npki_pattern_scores_highest_and_reit_excluded(self):
        out = es.run(date(2026, 11, 18), dry=True, get=fake, sleep=lambda s: None)
        by = {x["ticker"]: x for x in out["leads"]}
        self.assertIn("NPKI", by)
        self.assertNotIn("RRT", by)                       # 임대 부동산 이름 제외
        n = by["NPKI"]
        self.assertEqual(set(n["waves"]), {"grid", "datacenter"})
        self.assertTrue(n["substitute"] and n["critical"])
        self.assertEqual(n["strength"], 9.0)              # 3.5 + 반복 1 + 물결 1 + 추가 물결 0.5 + 집중 1(송전 2건) + 대체 1 + 핵심 1
        self.assertEqual(n["float_usd"], 683700000)
        self.assertEqual(out["leads"][0]["ticker"], "NPKI")

    def test_lease_share_bonus_and_size_gate(self):
        out = es.run(date(2026, 11, 18), dry=True, get=fake, sleep=lambda s: None)
        allc = {x["ticker"]: x for x in out["leads"]}
        self.assertIn("BRC", allc)                         # 리스 수익 30% → 가점으로 문턱 통과
        self.assertEqual(allc["BRC"]["lease_share"], 0.3)

    def test_pure_play_focus_beats_scattered(self):
        def g(url):
            if "EntityPublicFloat" in url:
                return json.dumps({"data": [{"cik": 7, "val": 6e8}, {"cik": 8, "val": 6e8}]})
            if "/frames/" in url:
                return json.dumps({"data": []})
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
            hits = []
            if '"rental fleet"' in q and "transmission" in q:
                hits = ["Pure Mat Co  (PMC)  (CIK 0000000007)"]       # 한 물결, 두 어구 → 집중
            if '"lease revenue"' in q and ('"hyperscale"' in q or '"defense budget"' in q):
                hits = ["Scatter Inc  (SCT)  (CIK 0000000008)"]      # 두 물결 한 번씩
            return json.dumps({"hits": {"hits": [{"_source": {"display_names": [n], "adsh": f"a{q}{i}", "file_date": "2026-01-01"}} for i, n in enumerate(hits)]}})
        out = es.run(date(2026, 11, 18), dry=True, get=g, sleep=lambda s: None)
        by = {x["ticker"]: x for x in out["leads"]}
        self.assertTrue(by["PMC"]["focus"])
        self.assertGreaterEqual(by["PMC"]["strength"], by.get("SCT", {"strength": 0})["strength"])

    def test_min_emit(self):
        out = es.run(date(2026, 11, 18), dry=True, get=fake, sleep=lambda s: None)
        self.assertTrue(all(x["strength"] >= es.cfg()["strength"]["min_emit"] for x in out["leads"]))

    def test_channel_registered_with_lens(self):
        import yaml
        ch = yaml.safe_load((ROOT / "config" / "discovery_channels.yaml").read_text(encoding="utf-8"))["channels"]["enabler"]
        self.assertEqual(ch["lens"], "enabler")
        t = (ROOT / "knowledge" / "methods" / "sector_lenses" / "enabler.md").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"(?m)^\d+\. ", t)), 7)


if __name__ == "__main__":
    unittest.main()
