"""Analysis 리포트 '구루 교차 점검' 절(ADR-050, 마스터 지시 2026-11-22 "넣어라") 오프라인 시험 — 절·요약 줄·재료 검사·숫자와 판정의 어긋남"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "tenbagger"))
import guru_view as gv  # noqa: E402
import playbook as pb  # noqa: E402

CFG = pb.cfg()
LIQ = ("중립", "10년물 20일 +5bp · 하이일드 스프레드 20일 +3bp")
SRC = "https://www.sec.gov/Archives/edgar/data/1/x.htm"
DP = {"consensus": {"rev": {"FY2026": 100, "FY2028": 169}},
      "financials": {"ebit_ttm": 20, "invested_capital": 100, "capex_ttm": 12, "da_ttm": 4, "sbc_ttm": 1},
      "profile": {"price": 10, "shares_basic": 30}, "tax": 0.25,
      "forward": {"ntm": {"eps": 1.0}, "horizons": {"2": {"eps": 1.5}}}, "multiples_now": {"pe_fwd": 12}}


def guru():
    return {"horizon_years": 7, "target_multiple": 5,
            "views": {"runway": {"verdict": "pass", "why": "참조 시장이 3배로 커진다", "evidence": "사업보고서 2025 " + SRC},
                      "moat_returns": {"verdict": "pass", "why": "전환 비용", "evidence": "DEF 14A"},
                      "reinvestment": {"verdict": "unknown", "why": "증설 수익률 미확인", "evidence": ""},
                      "people": {"verdict": "pass", "why": "창업자 지분 22%", "evidence": "위임장 2026"},
                      "change": {"verdict": "pass", "why": "추정 상향", "evidence": "실적 발표 자료"},
                      "mispricing": {"verdict": "fail", "why": "배수가 이미 높다", "evidence": ""}},
            "dissent": {"view": "mispricing", "why": "가격이 성장을 이미 담았다."},
            "hold": {"kpis": ["수주잔고 전년 대비", "매출총이익률"], "rule": "가격만 빠지고 지표가 살아 있으면 유지"}}


def texts(sec):
    out = []
    for b in sec["blocks"]:
        out += [str(b.get("text") or ""), str(b.get("title") or "")] + [str(i) for i in b.get("items") or [] if isinstance(i, str)]
        out += [str(c) for r in b.get("rows") or [] for c in r]
        for x in b.get("items") or []:
            if isinstance(x, dict):
                out += [str(x.get("title")), str(x.get("tag"))] + [str(v) for _, v in x.get("lines") or []]
    return "\n".join(out)


class TestCheck(unittest.TestCase):
    def test_report_does_not_require_pass_count(self):
        g = guru()
        for k in g["views"]:
            g["views"][k] = {"verdict": "fail", "why": "미달 이유"}
        g["dissent"] = {"view": "runway", "why": "전부 약하다"}
        self.assertEqual(gv.check({"guru": g}, CFG), [])        # 나쁜 회사도 리포트는 쓴다 — 구조만 본다

    def test_structure_is_required(self):
        self.assertTrue(gv.check({}, CFG)[0].startswith("datapack guru 없음"))
        g = guru()
        g["views"]["change"]["evidence"] = "경영진이 그렇게 말했다"
        g["hold"] = {"kpis": ["수주잔고"]}
        g.pop("dissent")
        err = " / ".join(gv.check({"guru": g}, CFG))
        self.assertIn("근거", err)
        self.assertIn("보유 규율", err)
        self.assertIn("dissent", err)

    def test_korean_document_names_count_as_evidence(self):
        for ev in ("실적 발표 자료", "위임장 2026", "반기보고서", "3분기 어닝콜", "決算短信"):
            g = guru()
            g["views"]["change"]["evidence"] = ev
            self.assertEqual(gv.check({"guru": g}, CFG), [], ev)


class TestSection(unittest.TestCase):
    def test_section_with_judgment(self):
        sec = gv.section(dict(DP, guru=guru()), None, wacc=0.10, c=CFG, liq=LIQ)
        self.assertEqual(sec["h2"], "구루 교차 점검")
        self.assertIn("통과 4 · 미달 1 · 미확인 1", sec["blocks"][0]["text"])
        self.assertIn("가장 약한 관점은 5배 경로와 시장이 모르는 이유", sec["blocks"][0]["text"])
        boxes = next(b for b in sec["blocks"] if b["type"] == "boxes")["items"]
        self.assertEqual([b["title"] for b in boxes], [CFG["views"][k]["name"] for k in gv.ORDER])
        self.assertEqual([b["tag"] for b in boxes], ["통과", "통과", "미확인", "통과", "통과", "미달"])
        t = texts(sec)
        self.assertIn("매출 경로 FY2026→FY2028 연 30.0%", t)
        self.assertIn("ROIC 15.0% · 자본비용 10.0%", t)
        self.assertIn("2년 뒤 EPS +50.0%", t)
        self.assertIn("7년에 5배 = 연 25.8% · 10배 = 연 38.9%", t)     # 표시할 때 한 번만 반올림한다(39.0%가 아니다)
        self.assertIn("38.9%", [c for b in sec["blocks"] if b["type"] == "table" for r in b["rows"] for c in r])
        self.assertIn("58.5%(희소)", t)
        self.assertIn("투자 논리 지표: 수주잔고 전년 대비 · 매출총이익률", t)
        self.assertIn("매매·비중 지시가 아니다", t)
        self.assertEqual(sec["_sources"], [SRC])                    # URL은 출처 목록으로 보낸다
        self.assertNotIn("http", t)
        self.assertNotIn("DEF", t)                                   # 서류 약자는 한글로(용어 풀이 점검에 걸리지 않게)
        self.assertEqual(sec["_warnings"], [])

    def test_section_without_judgment_shows_numbers_only(self):
        sec = gv.section(DP, None, wacc=None, c=CFG, liq=LIQ)
        t = texts(sec)
        self.assertIn("판정은 미확인", sec["blocks"][0]["text"])
        boxes = next(b for b in sec["blocks"] if b["type"] == "boxes")["items"]
        self.assertTrue(all(b["tag"] == "미확인" for b in boxes))
        self.assertIn("ROIC 15.0%", t)
        self.assertNotIn("· 자본비용", t)                             # 자본비용을 모르면 숫자 줄에 싣지 않는다
        self.assertNotIn("판정은 자체추론", t)

    def test_unknown_numbers_stay_unknown(self):
        t = texts(gv.section({}, None, c=CFG, liq=("미확인", "금리·신용 스프레드 자료 없음")))
        self.assertIn("매출 경로 미확인", t)
        self.assertIn("ROIC 미확인", t)
        self.assertIn("2년 뒤 EPS 미확인", t)

    def test_asset_light_reinvestment_wording(self):
        dp = dict(DP, financials=dict(DP["financials"], capex_ttm=3))      # 설비투자 3 < 감가상각 4
        t = texts(gv.section(dp, None, c=CFG, liq=LIQ))
        self.assertIn("설비 재투자율 0%(설비투자가 감가상각 이하", t)
        self.assertNotIn("지속 가능 성장 0.0%", t)                        # 0%를 '성장 불가'로 읽히게 두지 않는다

    def test_conflicts_between_verdict_and_numbers(self):
        dp = {"consensus": {"rev": {"FY2026": 100, "FY2028": 110}},      # 연 4.9% — 5년 2배 미달
              "financials": {"ebit_ttm": 5, "invested_capital": 100}, "tax": 0.2,   # ROIC 4%
              "forward": {"ntm": {"eps": 1.0}, "horizons": {"2": {"eps": 0.8}}},   # 2년 뒤 EPS −20%
              "guru": guru()}
        sec = gv.section(dp, None, wacc=0.09, c=CFG, liq=LIQ)
        w = " / ".join(sec["_warnings"])
        self.assertIn("5년 2배", w)
        self.assertIn("자본비용", w)
        self.assertIn("2년 뒤 EPS", w)
        self.assertEqual(len(sec["_warnings"]), 3)
        self.assertIn("숫자와 판정이 어긋난다", texts(sec))              # 절에도 그대로 싣는다
        g = guru()
        for k in ("runway", "moat_returns", "change"):
            g["views"][k] = {"verdict": "fail", "why": "숫자가 받쳐 주지 않는다"}
        self.assertEqual(gv.section(dict(dp, guru=g), None, wacc=0.09, c=CFG, liq=LIQ)["_warnings"], [])   # 미달로 쓰면 어긋남이 아니다

    def test_drawdown_line(self):
        saved = pb.drawdown
        try:
            pb.drawdown = lambda e: (-0.62, -0.70, 400)
            t = texts(gv.section(dict(DP, guru=guru()), "us-xyz", c=CFG, liq=LIQ))
            self.assertIn("일봉 400개 기간의 고점 대비 -62.0%", t)
            self.assertIn("재심사 구간", t)
            pb.drawdown = lambda e: (-0.10, -0.30, 400)
            self.assertNotIn("재심사 구간", texts(gv.section(dict(DP, guru=guru()), "us-xyz", c=CFG, liq=LIQ)))
        finally:
            pb.drawdown = saved


class TestSummary(unittest.TestCase):
    def test_summary_item(self):
        s = gv.summary_item(dict(DP, guru=guru()), None, c=CFG, liq=LIQ)
        self.assertEqual(s["q"], "구루 여섯 관점으로 보면 어떤가?")
        self.assertTrue(s["auto"])
        self.assertIn("**통과 4 · 미달 1 · 미확인 1**", s["a"])
        self.assertIn("판단 기간 7년, 그 안에 10배면 연 38.9%가 필요하다", s["a"])
        self.assertIn("가격이 성장을 이미 담았다. ", s["a"])              # 마침표가 겹치지 않는다
        self.assertNotIn("..", s["a"])

    def test_summary_without_judgment(self):
        s = gv.summary_item(DP, None, c=CFG, liq=LIQ)
        self.assertTrue(s["a"].startswith("판정 미확인"))
        self.assertIn("ROIC 15.0%", s["a"])


class TestWiring(unittest.TestCase):
    def test_layout_calls_guru_view_after_lynch(self):
        src = (ROOT / "scripts" / "tenbagger" / "report_layout.py").read_text(encoding="utf-8")
        self.assertLess(src.index("auto.append(lynch.summary_item(dp))"), src.index("auto.append(guru_view.summary_item("))
        self.assertLess(src.index("out.append(lynch.section(dp))"), src.index("out.append(guru_sec)"))
        self.assertLess(src.index("out.append(guru_sec)"), src.index("moat_section(dp), leader_view.report_section"))
        self.assertIn("guru_view.GATE_FROM", src)

    def test_gate_date_and_wording(self):
        self.assertRegex(gv.GATE_FROM, r"^\d{4}-\d{2}-\d{2}$")
        body = (ROOT / "scripts" / "tenbagger" / "guru_view.py").read_text(encoding="utf-8")
        self.assertNotIn("테제", body)
        self.assertNotIn("배수 사다리", body)                             # 리포트 금지 표기(report_layout.BANNED)
        for v in CFG["views"].values():                                   # 리포트에 실리는 질문에도 금지 표기가 없어야 한다
            self.assertNotIn("배수 사다리", v["name"] + v["ask"])

    def test_box_tag_is_readable(self):
        css = (ROOT / "scripts" / "tenbagger" / "report_html.py").read_text(encoding="utf-8")
        self.assertIn(".bx .tag{font-size:12px;font-weight:600;color:var(--c);background:none", css)   # 글자색 = 배경색이 되던 충돌(2026-11-22 화면 확인)


if __name__ == "__main__":
    unittest.main()
