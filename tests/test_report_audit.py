"""Proviser 당일 텐배거 리포트 3건 점검 시험 (마스터 지시 2026-10-29 — 당일 3건만, 사실·과정·결론 정량 평가)"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "proviser"))

import report_audit as ra  # noqa: E402


def report(probs=(0.3, 0.5, 0.2), stated="확률 가중 1.07배", kill_rows=3, extra=""):
    cases = [{"name": n, "value": v, "prob": p} for n, v, p in zip(("약세", "기본", "강세"), (50, 100, 200), probs)]
    return {"title": "t", "date": "2026-10-29", "ticker": "TST", "company": "Test", "biz": "b",
            "verdict": {"view": f"DCF 기본 1.05배 · {stated} {extra}"},
            "sections": [{"h2": "밸류에이션 — 맥킨지·IB 방식(v2 엔진)", "blocks": [{"type": "p", "text": "합리적 멀티플 동종사"}]},
                         {"h2": "판단 시나리오 — 12개월", "blocks": [{"type": "chart", "chart": {"kind": "scenario", "unit": "$", "current": 100, "cases": cases}}]},
                         {"h2": "킬 조건과 체크리스트", "blocks": [{"type": "table", "headers": ["조건", "의미"], "rows": [["a", "b"]] * kill_rows},
                                                            {"type": "p", "text": "11/12 실적 확인"}]}],
            "sources": ["https://www.sec.gov/x 8-K", "b", "c 보강 적용: D-1"]}


class TestReportAudit(unittest.TestCase):
    def test_only_that_day_latest_three(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "log.csv"
            log.write_text("date,id,ticker,html,view\n" + "".join(f"2026-10-29,id{i},T{i},x/{i}.html,v\n" for i in range(5))
                           + "2026-10-28,old,OLD,x/o.html,v\n", encoding="utf-8")
            saved, ra.LOG = ra.LOG, log
            try:
                rows = ra.day_reports("2026-10-29")
            finally:
                ra.LOG = saved
        self.assertEqual([r["id"] for r in rows], ["id2", "id3", "id4"])   # 그날 가장 최근 3건만
        self.assertTrue(all(r["date"] == "2026-10-29" for r in rows))        # 다른 날짜는 다루지 않는다

    def _audit(self, d, html="<svg></svg><svg></svg>공개 자료 기반 분석이며 투자 권유가 아님"):
        with tempfile.TemporaryDirectory() as t:
            jp, hp = Path(t) / "r.json", Path(t) / "r.html"
            jp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            hp.write_text(html, encoding="utf-8")
            res = ra.audit({"id": "no-such-entity", "ticker": "TST", "json": str(jp), "html": str(hp)})
        return {x["name"]: x for x in res["checks"]}, res["auto"]

    def test_conclusion_checks(self):
        ck, _ = self._audit(report())
        self.assertEqual(ck["시나리오 확률 합 = 1"]["status"], "통과")
        self.assertEqual(ck["확률 가중값 재계산"]["status"], "통과")        # (0.3×50 + 0.5×100 + 0.2×200)/100 = 1.05 ≈ 1.07(±0.05)
        self.assertEqual(ck["킬 조건 2~4 + 날짜"]["status"], "통과")
        self.assertEqual(ck["데이터 검증 10/10"]["status"], "실패")         # datapack 없음
        ck, _ = self._audit(report(probs=(0.3, 0.5, 0.3)))
        self.assertEqual(ck["시나리오 확률 합 = 1"]["status"], "실패")

    def test_prescriptive_and_units(self):
        ck, _ = self._audit(report(extra="지금 매수하라"))
        self.assertEqual(ck["처방 표현 없음·면책"]["status"], "실패")
        ck, _ = self._audit(report(), html="<svg></svg><svg></svg>매출 250억 달러 · 투자 권유가 아님")
        self.assertEqual(ck["금액 단위 $B·$M"]["status"], "실패")
        self.assertEqual(ck["차트 ≥ 3·렌더 일치"]["status"], "실패")       # 차트 1개

    def test_final_score(self):
        f, rub = ra.final_score(8.0, [1.8, 1.6, 1.5, 1.7, 1.4], {"auto_weight": 0.4})
        self.assertEqual(rub, 8.0)
        self.assertEqual(f, 8.0)
        f, _ = ra.final_score(6.5, [2, 2, 2, 2, 2], {"auto_weight": 0.4})
        self.assertEqual(f, 8.6)


if __name__ == "__main__":
    unittest.main()
