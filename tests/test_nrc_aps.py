"""NRC ADAMS 공개 문서 수집기(2026-11-22 마스터 키 입력, TODO 21-64)"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import common, nrc_aps as N  # noqa: E402


def resp(*docs):
    return lambda req: json.dumps({"count": len(docs), "results": [{"document": d} for d in docs]}).encode()


DOC = {"AccessionNumber": "ML26300A001", "DocumentTitle": "Oklo Inc. - Request for Additional Information", "DocumentType": ["Letter"],
       "AddresseeAffiliation": ["Oklo, Inc."], "AuthorAffiliation": ["NRC/NRR"], "DateAddedTimestamp": "2026-11-21 08:00", "Url": "https://www.nrc.gov/docs/x.pdf"}
NOISE = dict(DOC, AccessionNumber="ML26300A002", AddresseeAffiliation=["NRC"], DocumentTitle="Inspection Manual Change Notice")


class Nrc(unittest.TestCase):
    def setUp(self):
        self.mem = {}
        mock.patch.object(common, "load_state", side_effect=lambda n, d=None: self.mem.get(n, d)).start()
        mock.patch.object(common, "save_state", side_effect=lambda n, v: self.mem.__setitem__(n, v)).start()
        mock.patch.object(N, "cfg", return_value={"companies": [{"id": "co-oklo", "ticker": "OKLO", "names": ["Oklo"]}], "signal": "(?i)additional information|license"}).start()

    def tearDown(self):
        mock.patch.stopall()

    def test_baseline_then_new_signal_only(self):
        self.assertEqual(N.poll({"NRC_APS_KEY": "k"}, post=resp(DOC)), [])   # 첫 회차 = 기준선
        new = dict(DOC, AccessionNumber="ML26300A003")
        got = N.poll({"NRC_APS_KEY": "k"}, post=resp(new, NOISE))
        self.assertEqual(len(got), 1)
        self.assertIn("OKLO", got[0]["title"])

    def test_no_key_skips(self):
        self.assertEqual(N.poll({}, post=resp(DOC)), [])


if __name__ == "__main__":
    unittest.main()
