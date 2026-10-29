"""노션 Stocks 우선 리포트 시험 (마스터 지시 2026-10-30 — ±7일 어닝콜 스크립트·컨센서스 입력 종목부터)"""
import csv
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))

import notion_stocks as ns  # noqa: E402
import pick_report  # noqa: E402

CALL = """Quanta Services Q3 2026 Earnings Call — October 29, 2026
Prepared Remarks
Operator: Good morning.
Earl Austin — CEO: Record backlog.
Jayshree — CFO: Revenue $12.0B.
Question-and-Answer Session
Analyst — Goldman Sachs: data center demand?
컨센서스: 매출 $11.0B, EPS $5.02 (est.)"""


class TestNotionStocks(unittest.TestCase):
    def test_title(self):
        self.assertEqual(ns.parse_title("콴타서비스 PWR"), ("콴타서비스", "PWR"))
        self.assertEqual(ns.parse_title("삼성전기(009150)"), ("삼성전기", "009150"))
        self.assertIsNone(ns.parse_title("OCP 2026")[1])   # 연도는 티커가 아니다(테마 페이지)
        self.assertIsNone(ns.parse_title("해양시추")[1])

    def test_classify(self):
        r = ns.classify(CALL, "2026-10-29", today=date(2026, 10, 30))
        self.assertTrue(r["has_transcript"] and r["has_consensus"] and r["has_ib"])
        self.assertEqual(r["call_date"], "2026-10-29")
        self.assertEqual(r["date_basis"], "본문 날짜")
        r2 = ns.classify("메모: 관심 종목", "2026-10-29")
        self.assertFalse(r2["has_transcript"] or r2["has_consensus"])

    def test_pick_window_and_repeat(self):
        idx = {"pages": [{"page_id": "a", "company": "콴타서비스", "ticker": "PWR", "call_date": "2026-10-29", "date_basis": "본문 날짜",
                          "has_transcript": True, "has_consensus": True, "has_ib": True},
                         {"page_id": "b", "company": "옛 종목", "ticker": "OLDX", "call_date": "2026-10-01", "has_transcript": True, "has_consensus": True},
                         {"page_id": "c", "company": "컨센서스 없음", "ticker": "NOCS", "call_date": "2026-10-29", "has_transcript": True, "has_consensus": False}]}
        self.assertEqual([p["ticker"] for p in ns.eligible(date(2026, 10, 30), idx)], ["PWR"])   # ±7일·둘 다 입력된 것만
        with tempfile.TemporaryDirectory() as d:
            ip, lp = Path(d) / "idx.json", Path(d) / "log.csv"
            ip.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
            saved = (ns.INDEX, pick_report.LOG)
            ns.INDEX, pick_report.LOG = ip, lp
            try:
                hit = pick_report.notion_pick(date(2026, 10, 30), {"co-quanta-services": {"id": "co-quanta-services", "name": "Quanta", "ticker": "PWR"}})
                self.assertEqual(hit["id"], "co-quanta-services")
                self.assertIn("노션 Stocks", hit["reason"])
                with lp.open("w", encoding="utf-8", newline="") as f:   # 콜 날짜 이후 이미 썼으면 건너뛴다
                    w = csv.DictWriter(f, fieldnames=pick_report.FIELDS)
                    w.writeheader()
                    w.writerow({"date": "2026-10-29", "id": "co-quanta-services", "ticker": "PWR", "html": "x", "view": "v"})
                self.assertIsNone(pick_report.notion_pick(date(2026, 10, 30), {}))
            finally:
                ns.INDEX, pick_report.LOG = saved


if __name__ == "__main__":
    unittest.main()
