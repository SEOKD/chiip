"""중국 본토 반도체 IR 수집 — 문서 종류·기간·실적설명회 전문·합동 설명회 거르기 (마스터 지시 2026-11-17)"""
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "radar"))
from pollers import cn_ir  # noqa: E402


class TestCnIr(unittest.TestCase):
    def test_kind_of(self):
        self.assertEqual(cn_ir.kind_of("2026年第三季度报告"), "report")
        self.assertEqual(cn_ir.kind_of("2026年半年度报告摘要"), None)   # 摘要는 뺀다
        self.assertEqual(cn_ir.kind_of("关于召开2026年第三季度业绩说明会的公告"), None)   # 개최 예고는 자료가 아니다
        self.assertEqual(cn_ir.kind_of("2026年第三季度业绩说明会召开情况的公告"), "qa")
        self.assertEqual(cn_ir.kind_of("投资者关系活动记录表（2026年11月）"), "qa")
        self.assertEqual(cn_ir.kind_of("2026年半年度业绩预告的自愿性披露公告"), "prelim")

    def test_period(self):
        self.assertEqual(cn_ir.period("中微公司2026年第三季度业绩说明会"), "2026Q3")
        self.assertEqual(cn_ir.period("2026年半年度报告"), "2026H1")
        self.assertEqual(cn_ir.period("2025年年度业绩说明会"), "2025FY")

    def test_transcript_joint_meeting_filters_company(self):
        recs = [{"questionType": 4, "content": "欢迎", "crtTime": "2026-11-16 15:00:00"},
                {"questionType": 2, "companyId": 1, "guestName": "尹志尧", "guestTitle": "董事长", "questionContent": "毛利率？", "content": "保持稳定", "crtTime": "2026-11-16 15:10:00"},
                {"questionType": 2, "companyId": 2, "guestName": "别人", "questionContent": "别的公司", "content": "无关", "crtTime": "2026-11-16 15:11:00"}]
        with mock.patch.object(cn_ir, "_rs", lambda p, d: {"records": recs, "total": 3}):
            text, n = cn_ir.rs_transcript(9, cid=1)
        self.assertEqual(n, 1)
        self.assertIn("问: 毛利率？", text)
        self.assertIn("答 尹志尧(董事长): 保持稳定", text)
        self.assertNotIn("无关", text)

    def test_activity_dates_from_startdate(self):
        rec = [{"id": 42013, "activityType": 1, "title": "中微公司2026年第三季度业绩说明会", "startDate": "2026-11-16 00:00:00",
                "endDate": "2026-11-16 00:00:00", "startTime": "1970-01-01 16:00:00", "endTime": "1970-01-01 17:00:00", "isMulti": False}]
        with mock.patch.object(cn_ir, "_rs", lambda p, d: {"records": rec}):
            a = cn_ir.rs_activities(1)[0]
        self.assertEqual((a["start"], a["end"]), ("2026-11-16 16:00:00", "2026-11-16 17:00:00"))
        self.assertLess(datetime.fromisoformat(a["end"]), datetime(2026, 11, 17))


if __name__ == "__main__":
    unittest.main()
