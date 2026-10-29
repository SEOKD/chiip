"""대만 法說會 감지·IR 프로필 (마스터 지시 2026-10-30, knowledge/methods/tw_hk_ir_qa_procedure.md)"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))

from pollers import tw_disclosure as tw  # noqa: E402


class TestConference(unittest.TestCase):
    def test_invited_roc_date_broker(self):
        c = tw.parse_conference("本公司受邀參加凱基證券舉辦之法人說明會 1.召開法人說明會之日期:115/11/05 2.地點:台北")
        self.assertEqual(c["date"], "2026-11-05")      # 민국 115년 → 2026
        self.assertEqual(c["host"], "受邀")
        self.assertEqual(c["broker"], "凱基證券")
        self.assertFalse(c["video"])

    def test_self_hosted_with_video_and_english(self):
        c = tw.parse_conference("本公司召開法人說明會 日期:2026年10月30日 將以英文進行並提供影音連結")
        self.assertEqual((c["date"], c["host"], c["broker"]), ("2026-10-30", "自辦", None))
        self.assertTrue(c["video"] and c["english"])

    def test_missing_date_stays_none(self):
        self.assertIsNone(tw.parse_conference("本公司將召開法人說明會")["date"])   # 추측 금지

    def test_profile_frequency(self):
        store = {}
        with mock.patch.object(tw.common, "load_state", lambda n, d: store.get(n, d)), \
             mock.patch.object(tw.common, "save_state", lambda n, v: store.__setitem__(n, v)):
            for d in ("2026-02-10", "2026-05-08", "2026-08-07", "2026-11-05"):
                p = tw.update_profile("2330", "TSMC", {"date": d, "host": "自辦", "broker": None, "video": True, "english": True}, d + "T07:00:00+08:00")
            tw.update_profile("2330", "TSMC", {"date": "2026-11-05", "host": "自辦", "broker": None, "video": True, "english": True}, "2026-11-01T07:00:00+08:00")
        p = store["tw_ir_profile"]["2330"]
        self.assertEqual((p["freq"], p["freq_per_year"], len(p["events"])), ("분기", 4, 4))   # 같은 날 재공고는 중복 아님
        self.assertTrue(p["video_seen"])

    def test_pulse_keeps_chinese_ir_event(self):
        import pulse
        it = {"source_id": "src-tw-disclosure", "ir_event": "法說會", "language": "zh", "title": "🎙 台積電(2330) 法說會 공고"}
        cls = "IR 질의응답" if it.get("ir_event") else pulse.class_of(it["source_id"])
        self.assertTrue(pulse.relevant(it, cls))


if __name__ == "__main__":
    unittest.main()
